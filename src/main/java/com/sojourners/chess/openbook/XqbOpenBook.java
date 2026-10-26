package com.sojourners.chess.openbook;

import com.sojourners.chess.board.ChessBoard;
import com.sojourners.chess.model.BookData;
import com.sojourners.chess.util.ZobristUtils;

import java.io.File;
import java.sql.*;
import java.util.ArrayList;
import java.util.List;

public class XqbOpenBook implements OpenBook {

    private Connection connection;

    private String name;

    public XqbOpenBook(String bookPath) throws ClassNotFoundException, SQLException {
        Class.forName("org.sqlite.JDBC");
        this.connection = DriverManager.getConnection("jdbc:sqlite:" + bookPath);
        this.name = new File(bookPath).getName();
    }

    @Override
    public List<BookData> get(char[][] board, boolean redGo) {
        XQKEY xqKey = new XQKEY();
        String fenCode = ChessBoard.fenCode(board, redGo);
        FenToKey(fenCode, xqKey);
        return BookQuery(xqKey);
    }

    @Override
    public List<BookData> get(String fenCode, boolean onlyFinalPhase) {
        return null;
    }

    @Override
    public void close() {
        try {
            this.connection.close();

        } catch (Exception e) {
            e.printStackTrace();
        }
    }


    static class XQKEY {
        byte[] Key = new byte[128];
        int KeyLen;
        boolean MirrorUD;
        boolean MirrorLR;
        int Rows;
        int Cols;
    }

    private int GetRowsAndCols(String fen, int[] rowsCols) {
        int rows = 1;
        int cols = 0;
        boolean calcCols = true;
        for (int i = 0; fen.charAt(i) != ' '; i++) {
            char ch = fen.charAt(i);
            if (ch == '/') {
                rows++;
                calcCols = false;
            } else if (calcCols) {
                if (ch >= '0' && ch <= '9') {
                    cols += ch - '0';
                } else {
                    cols += 1;
                }
            }
        }
        rowsCols[0] = rows;
        rowsCols[1] = cols;
        return rows * cols;
    }

    private void FenToKey(String fen, XQKEY xqKey) {
        int turn = fen.charAt(fen.indexOf(' ') + 1) != 'b' ? 1 : 0;
        int[] rc = new int[2];
        int size = GetRowsAndCols(fen, rc);
        xqKey.Rows = rc[0];
        xqKey.Cols = rc[1];
        byte[] ary = new byte[size];
        for (int i = 0; i < size; i++) ary[i] = (byte) -1;
        for (int i = 0, index = 0; fen.charAt(i) != ' ' && index < size; i++) {
            char ch = fen.charAt(i);
            if (ch >= '0' && ch <= '9') {
                index += ch - '0';
            } else if (ch != '/') {
                char mapped = turn == 0 ? (char) (ch ^ 0x20) : ch;
                byte val = -1;
                switch (mapped) {
                    case 'X':
                    case 'x': val = 0; break;
                    case 'R': val = 1; break;
                    case 'N': val = 2; break;
                    case 'B': val = 3; break;
                    case 'A': val = 4; break;
                    case 'K': val = 5; break;
                    case 'C': val = 6; break;
                    case 'P': val = 7; break;
                    case 'r': val = 9; break;
                    case 'n': val = 10; break;
                    case 'b': val = 11; break;
                    case 'a': val = 12; break;
                    case 'k': val = 13; break;
                    case 'c': val = 14; break;
                    case 'p': val = 15; break;
                }
                ary[index++] = val;
            }
        }
        xqKey.MirrorUD = false;
        if (turn == 0) {
            for (int row = 0; row < xqKey.Rows / 2; row++) {
                for (int col = 0; col < xqKey.Cols; col++) {
                    int index = row * xqKey.Cols + col;
                    int index2 = (xqKey.Rows - 1 - row) * xqKey.Cols + (xqKey.Cols - 1 - col);
                    byte tmp = ary[index];
                    ary[index] = ary[index2];
                    ary[index2] = tmp;
                }
            }
            xqKey.MirrorUD = true;
        }
        xqKey.MirrorLR = false;
        boolean lrDone = false;
        for (int row = 0; row < xqKey.Rows && !lrDone; row++) {
            for (int col = 0; col < xqKey.Cols / 2 && !lrDone; col++) {
                int index = row * xqKey.Cols + col;
                int index2 = row * xqKey.Cols + (xqKey.Cols - 1 - col);
                if (ary[index] != ary[index2]) {
                    xqKey.MirrorLR = ary[index2] > ary[index];
                    lrDone = true;
                }
            }
        }
        if (xqKey.MirrorLR) {
            for (int row = 0; row < xqKey.Rows; row++) {
                for (int col = 0; col < xqKey.Cols / 2; col++) {
                    int index = row * xqKey.Cols + col;
                    int index2 = row * xqKey.Cols + (xqKey.Cols - col - 1);
                    byte tmp = ary[index];
                    ary[index] = ary[index2];
                    ary[index2] = tmp;
                }
            }
        }
        xqKey.KeyLen = 0;
        int buffer = 0;
        int bufferBits = 32;
        int codeBits = 4;
        int bits = 0;
        for (int index = 0; index < size; index++) {
            if (ary[index] == -1) {
                bits++;
            } else {
                buffer |= 1 << (bufferBits - bits - 1);
                buffer |= (ary[index] & 0xFF) << (bufferBits - bits - 1 - codeBits);
                bits += 1 + codeBits;
            }
            int nextBits = (index == size - 1) ? 0 : ((ary[index + 1] == -1) ? 1 : codeBits + 1);
            if (index == size - 1 || bufferBits - bits < nextBits) {
                int threshold = index == size - 1 ? 1 : 8;
                while (bits >= threshold) {
                    xqKey.Key[xqKey.KeyLen++] = (byte) ((buffer >>> (bufferBits - 8)) & 0xFF);
                    buffer <<= 8;
                    bits -= 8;
                }
            }
        }
    }

    private int MirrorMove(int move, boolean mirrorUD, boolean mirrorLR, int rows, int cols) {
        if (mirrorUD || mirrorLR) {
            int fromRow = move >> 12;
            int fromCol = (move >> 8) & 0xF;
            int toRow = (move >> 4) & 0xF;
            int toCol = move & 0xF;
            if (mirrorUD) {
                fromRow = rows - 1 - fromRow;
                toRow = rows - 1 - toRow;
                fromCol = cols - 1 - fromCol;
                toCol = cols - 1 - toCol;
            }
            if (mirrorLR) {
                fromCol = cols - 1 - fromCol;
                toCol = cols - 1 - toCol;
            }
            move = (fromRow << 12) | (fromCol << 8) | (toRow << 4) | toCol;
        }
        return move;
    }

    private List<BookData> BookQuery(XQKEY xqKey) {
        StringBuilder sql = new StringBuilder("select Id,Move,Score,Win,Draw,Lost,Valid,Memo from book where key=x'");
        for (int i = 0; i < xqKey.KeyLen; i++) {
            sql.append(String.format("%02X", xqKey.Key[i] & 0xFF));
        }
        sql.append("'");

        List<BookData> results = new ArrayList<>();
        try (Statement stmt = this.connection.createStatement(); ResultSet rs = stmt.executeQuery(sql.toString())) {
            while (rs.next()) {
                BookData bd = new BookData();
                bd.setScore(rs.getInt("Score"));
                bd.setWinNum(rs.getInt("Win"));
                bd.setDrawNum(rs.getInt("Draw"));
                bd.setLoseNum(rs.getInt("Lost"));
                int winRate = (int) (10000 * (bd.getWinNum() + bd.getDrawNum() / 2.0d) / (bd.getWinNum() + bd.getDrawNum() + bd.getLoseNum()));
                bd.setWinRate(winRate / 100d);
                bd.setNote(rs.getString("Memo"));
                int vmove = MirrorMove(rs.getInt("Move"), xqKey.MirrorUD, xqKey.MirrorLR, xqKey.Rows, xqKey.Cols);
                int from = vmove >> 8;
                int to = vmove & 0xFF;
//                System.out.println("move:(row " + (from >> 4) + ",col " + (from & 0xF) + ")->(row " + (to >> 4) + ",col " + (to & 0xF) + "),score:" );
                bd.setMove(ChessBoard.stepForEngine(from & 0xF, from >> 4, to & 0xF, to >> 4));

                bd.setSource(this.name);
                results.add(bd);
            }

        } catch (SQLException e) {
            e.printStackTrace();
        }

        return results;
    }
}
