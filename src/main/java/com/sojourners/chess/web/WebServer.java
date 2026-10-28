package com.sojourners.chess.web;

import com.sojourners.chess.model.ThinkData;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Supplier;

/**
 * 内嵌 HTTP 服务，供外部工具（如直播辅助脚本、浏览器）读取当前对局的 FEN 与引擎分析，
 * 并在观战模式下提供走子控制接口。
 * <p>
 * 使用 JDK 自带 com.sun.net.httpserver，无需额外依赖。
 * <p>
 * 接口：
 * <pre>
 *   GET /            简易说明页
 *   GET /api/fen     当前局面 FEN + 行棋方 + 棋盘
 *   GET /api/analysis 当前引擎分析（多 PV）
 *   GET /api/state   fen 与 analysis 的合并快照
 *   POST /api/move   观战模式下按指定着法走子，body: {"move":"e2e4"} 或 move=e2e4
 * </pre>
 */
public class WebServer {

    /**
     * 观战模式走子控制回调。返回 true 表示已接受走子指令。
     */
    public interface MoveControl {
        boolean move(String move);
    }

    private final HttpServer server;
    private final Supplier<WebSnapshot> snapshotSupplier;
    private final MoveControl moveControl;
    private final ExecutorService executor;

    public WebServer(String host, int port, Supplier<WebSnapshot> snapshotSupplier, MoveControl moveControl) throws IOException {
        this.snapshotSupplier = snapshotSupplier;
        this.moveControl = moveControl;
        this.executor = Executors.newCachedThreadPool();
        this.server = HttpServer.create(new InetSocketAddress(host, port), 0);
        this.server.setExecutor(this.executor);
        this.server.createContext("/", this::handle);
    }

    public void start() {
        server.start();
    }

    public void stop() {
        server.stop(0);
        executor.shutdown();
    }

    public String getHost() {
        return server.getAddress().getHostString();
    }

    public int getPort() {
        return server.getAddress().getPort();
    }

    private void handle(HttpExchange ex) throws IOException {
        try {
            String method = ex.getRequestMethod();
            if ("OPTIONS".equalsIgnoreCase(method)) {
                addCors(ex);
                ex.sendResponseHeaders(204, -1);
                return;
            }
            String path = ex.getRequestURI().getPath();
            if ("/api/move".equals(path)) {
                handleMove(ex);
                return;
            }
            if (!"GET".equalsIgnoreCase(method)) {
                addCors(ex);
                send(ex, 405, "application/json; charset=utf-8",
                        "{\"error\":\"method not allowed, use GET\"}".getBytes(StandardCharsets.UTF_8));
                return;
            }
            switch (path) {
                case "/":
                case "/index.html":
                    addCors(ex);
                    send(ex, 200, "text/html; charset=utf-8", indexHtml().getBytes(StandardCharsets.UTF_8));
                    break;
                case "/api/fen":
                    addCors(ex);
                    send(ex, 200, "application/json; charset=utf-8", fenJson().getBytes(StandardCharsets.UTF_8));
                    break;
                case "/api/analysis":
                    addCors(ex);
                    send(ex, 200, "application/json; charset=utf-8", analysisJson().getBytes(StandardCharsets.UTF_8));
                    break;
                case "/api/state":
                    addCors(ex);
                    send(ex, 200, "application/json; charset=utf-8", stateJson().getBytes(StandardCharsets.UTF_8));
                    break;
                default:
                    addCors(ex);
                    send(ex, 404, "application/json; charset=utf-8",
                            "{\"error\":\"not found\"}".getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception e) {
            String msg = e.getMessage() == null ? "internal error" : e.getMessage();
            send(ex, 500, "application/json; charset=utf-8",
                    ("{\"error\":\"" + escape(msg) + "\"}").getBytes(StandardCharsets.UTF_8));
        } finally {
            ex.close();
        }
    }

    /**
     * 处理观战模式走子控制：POST /api/move，body/query 传入引擎格式着法 move。
     * 程序校验盘面合法性并做重复走子去重后落子，响应回传实际着法。
     */
    private void handleMove(HttpExchange ex) throws IOException {
        addCors(ex);
        if (!"POST".equalsIgnoreCase(ex.getRequestMethod())) {
            send(ex, 405, "application/json; charset=utf-8",
                    "{\"error\":\"method not allowed, use POST\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        String move = extractMove(ex);
        if (move == null) {
            send(ex, 400, "application/json; charset=utf-8",
                    "{\"error\":\"missing or invalid 'move'\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (moveControl == null || !moveControl.move(move)) {
            send(ex, 403, "application/json; charset=utf-8",
                    "{\"error\":\"control not allowed (must be in watch mode)\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        String body = "{\"ok\":true,\"move\":\"" + move + "\"}";
        send(ex, 200, "application/json; charset=utf-8", body.getBytes(StandardCharsets.UTF_8));
    }

    /** 从 query / JSON body / form body 中提取 move 字段 */
    private String extractMove(HttpExchange ex) throws IOException {
        String query = ex.getRequestURI().getRawQuery();
        if (query != null && !query.isEmpty()) {
            String m = parseParams(query).get("move");
            if (m != null && !m.isEmpty()) {
                return m;
            }
        }
        byte[] buf = ex.getRequestBody().readAllBytes();
        String body = new String(buf, StandardCharsets.UTF_8).trim();
        if (body.isEmpty()) {
            return null;
        }
        if (body.startsWith("{")) {
            int i = body.indexOf("move");
            if (i < 0) {
                return null;
            }
            int q = body.indexOf('"', i + 5);
            if (q < 0) {
                return null;
            }
            int q2 = body.indexOf('"', q + 1);
            if (q2 < 0) {
                return null;
            }
            return body.substring(q + 1, q2);
        }
        String m = parseParams(body).get("move");
        return (m != null && !m.isEmpty()) ? m : null;
    }

    private Map<String, String> parseParams(String s) {
        Map<String, String> map = new HashMap<>();
        if (s == null || s.isEmpty()) {
            return map;
        }
        for (String kv : s.split("&")) {
            int eq = kv.indexOf('=');
            if (eq > 0) {
                map.put(kv.substring(0, eq), kv.substring(eq + 1));
            }
        }
        return map;
    }

    private void addCors(HttpExchange ex) {
        ex.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
        ex.getResponseHeaders().set("Access-Control-Allow-Methods", "GET, OPTIONS");
        ex.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
    }

    private void send(HttpExchange ex, int code, String contentType, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", contentType);
        ex.sendResponseHeaders(code, body.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(body);
        }
    }

    private WebSnapshot snapshot() {
        WebSnapshot s = snapshotSupplier.get();
        if (s == null) {
            throw new IllegalStateException("snapshot timeout");
        }
        return s;
    }

    private String fenJson() {
        WebSnapshot s = snapshot();
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"fen\":\"").append(escape(s.fen)).append("\",");
        sb.append("\"redToMove\":").append(s.redToMove).append(',');
        sb.append("\"sideToMove\":\"").append(s.redToMove ? "red" : "black").append("\",");
        sb.append("\"isReverse\":").append(s.isReverse).append(',');
        sb.append("\"board\":").append(boardJson(s.board));
        sb.append('}');
        return sb.toString();
    }

    private String analysisJson() {
        WebSnapshot s = snapshot();
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"engineLoaded\":").append(s.engineLoaded).append(',');
        sb.append("\"engineName\":\"").append(escape(s.engineName == null ? "" : s.engineName)).append("\",");
        sb.append("\"analysisMode\":").append(s.analysisMode).append(',');
        sb.append("\"thinking\":").append(s.thinking).append(',');
        sb.append("\"count\":").append(s.lines == null ? 0 : s.lines.size()).append(',');
        sb.append("\"lines\":").append(linesJson(s.lines)).append(',');
        sb.append("\"best\":").append(bestJson(s.lines));
        sb.append('}');
        return sb.toString();
    }

    private String stateJson() {
        WebSnapshot s = snapshot();
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"fen\":\"").append(escape(s.fen)).append("\",");
        sb.append("\"redToMove\":").append(s.redToMove).append(',');
        sb.append("\"sideToMove\":\"").append(s.redToMove ? "red" : "black").append("\",");
        sb.append("\"isReverse\":").append(s.isReverse).append(',');
        sb.append("\"board\":").append(boardJson(s.board)).append(',');
        sb.append("\"engineLoaded\":").append(s.engineLoaded).append(',');
        sb.append("\"engineName\":\"").append(escape(s.engineName == null ? "" : s.engineName)).append("\",");
        sb.append("\"analysisMode\":").append(s.analysisMode).append(',');
        sb.append("\"thinking\":").append(s.thinking).append(',');
        sb.append("\"analysis\":{");
        sb.append("\"count\":").append(s.lines == null ? 0 : s.lines.size()).append(',');
        sb.append("\"lines\":").append(linesJson(s.lines)).append(',');
        sb.append("\"best\":").append(bestJson(s.lines));
        sb.append('}');
        sb.append('}');
        return sb.toString();
    }

    private String boardJson(char[][] board) {
        StringBuilder sb = new StringBuilder();
        sb.append('[');
        if (board != null) {
            for (int i = 0; i < board.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append('[');
                char[] row = board[i];
                for (int j = 0; j < row.length; j++) {
                    if (j > 0) {
                        sb.append(',');
                    }
                    sb.append('"').append(row[j] == ' ' ? " " : String.valueOf(row[j])).append('"');
                }
                sb.append(']');
            }
        }
        sb.append(']');
        return sb.toString();
    }

    private String linesJson(List<ThinkData> lines) {
        StringBuilder sb = new StringBuilder();
        sb.append('[');
        if (lines != null) {
            for (int i = 0; i < lines.size(); i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append(lineJson(lines.get(i)));
            }
        }
        sb.append(']');
        return sb.toString();
    }

    private String bestJson(List<ThinkData> lines) {
        if (lines == null || lines.isEmpty()) {
            return "null";
        }
        ThinkData best = lines.get(0);
        for (ThinkData td : lines) {
            if (td.getPv() != null && td.getPv() == 1) {
                best = td;
                break;
            }
        }
        return lineJson(best);
    }

    private String lineJson(ThinkData td) {
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"pv\":").append(num(td.getPv())).append(',');
        sb.append("\"depth\":").append(num(td.getDepth())).append(',');
        sb.append("\"score\":").append(num(td.getScore())).append(',');
        sb.append("\"mate\":").append(num(td.getMate())).append(',');
        sb.append("\"nps\":").append(num(td.getNps())).append(',');
        sb.append("\"timeMs\":").append(num(td.getTime())).append(',');
        sb.append("\"bestMove\":").append(moveAt(td.getDetail(), 0)).append(',');
        sb.append("\"moves\":").append(movesJson(td.getDetail())).append(',');
        sb.append("\"moveCn\":").append(str(td.getBody()));
        sb.append('}');
        return sb.toString();
    }

    private String movesJson(List<String> detail) {
        StringBuilder sb = new StringBuilder();
        sb.append('[');
        if (detail != null) {
            for (int i = 0; i < detail.size(); i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append(str(detail.get(i)));
            }
        }
        sb.append(']');
        return sb.toString();
    }

    private String moveAt(List<String> detail, int idx) {
        if (detail == null || idx < 0 || idx >= detail.size()) {
            return "null";
        }
        return str(detail.get(idx));
    }

    private String str(String s) {
        return s == null ? "null" : "\"" + escape(s) + "\"";
    }

    private String num(Number n) {
        return n == null ? "null" : String.valueOf(n);
    }

    private static String escape(String s) {
        if (s == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.toString();
    }

    private String indexHtml() {
        String fenUrl = "http://" + getHost() + ":" + getPort() + "/api/state";
        return "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>TCHESS WEB</title></head>"
                + "<body style=\"font-family:system-ui,sans-serif;margin:40px;\">"
                + "<h2>TCHESS 对外数据服务</h2>"
                + "<p>服务已启动，访问以下接口读取当前对局：</p>"
                + "<ul>"
                + "<li><code>GET /api/fen</code> — 当前局面 FEN、行棋方、棋盘</li>"
                + "<li><code>GET /api/analysis</code> — 当前引擎分析（多 PV）</li>"
                + "<li><code>GET /api/state</code> — FEN 与分析合并快照</li>"
                + "<li><code>POST /api/move</code> — 观战模式下按指定着法走子（body: <code>{\"move\":\"e2e4\"}</code>）</li>"
                + "</ul>"
                + "<p>提示：要让 <code>/api/analysis</code> 有数据，需加载引擎并开启「分析模式」或让引擎参与走棋；"
                + "<code>/api/move</code> 仅在「观战模式」下可用。</p>"
                + "<p><a href=\"" + fenUrl + "\">查看当前快照</a></p>"
                + "</body></html>";
    }
}
