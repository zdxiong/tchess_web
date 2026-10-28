package com.sojourners.chess.web;

import com.sojourners.chess.model.ThinkData;

import java.util.List;

/**
 * 对外暴露的当前对局快照。
 * <p>
 * 该对象在 JavaFX 应用线程上构建，避免与棋盘、棋谱等 UI 状态产生数据竞争。
 */
public class WebSnapshot {

    /** 当前局面 FEN，例如 "rnbakabnr/9/.../RNBAKABNR w - - 0 1" */
    public final String fen;

    /** 当前是否红方走棋 */
    public final boolean redToMove;

    /** 棋盘是否翻转显示 */
    public final boolean isReverse;

    /** 棋盘快照 10x9，行为黑方(上)到红方(下)，列从第9列到第1列，空格为 ' ' */
    public final char[][] board;

    /** 引擎当前思考结果列表（多 PV，按 pv 升序），无分析时为空 */
    public final List<ThinkData> lines;

    /** 是否处于分析模式 */
    public final boolean analysisMode;

    /** 引擎是否正在思考 */
    public final boolean thinking;

    /** 引擎是否已加载 */
    public final boolean engineLoaded;

    /** 引擎名称，未加载为空串 */
    public final String engineName;

    /** 是否处于观战模式（观战模式下允许外部通过 /api/move 控制走子） */
    public final boolean controlEnabled;

    public WebSnapshot(String fen, boolean redToMove, boolean isReverse, char[][] board,
                       List<ThinkData> lines, boolean analysisMode, boolean thinking,
                       boolean engineLoaded, String engineName, boolean controlEnabled) {
        this.fen = fen;
        this.redToMove = redToMove;
        this.isReverse = isReverse;
        this.board = board;
        this.lines = lines;
        this.analysisMode = analysisMode;
        this.thinking = thinking;
        this.engineLoaded = engineLoaded;
        this.engineName = engineName;
        this.controlEnabled = controlEnabled;
    }
}
