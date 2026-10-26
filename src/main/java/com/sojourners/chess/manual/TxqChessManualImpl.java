package com.sojourners.chess.manual;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class TxqChessManualImpl implements ChessManualService {

    @Override
    public ChessManual openChessManual(File file) {
        ObjectInputStream os = null;
        try {
            os = new ObjectInputStream(new FileInputStream(file));
            return (ChessManual) os.readObject();
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            try {
                if (os != null)
                    os.close();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
        return null;
    }

    @Override
    public void saveChessManual(ChessManual cm, File file) {
        ObjectOutputStream os = null;
        try {
            os = new ObjectOutputStream(new FileOutputStream(file));
            os.writeObject(cm);
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            try {
                if (os != null)
                    os.close();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}
