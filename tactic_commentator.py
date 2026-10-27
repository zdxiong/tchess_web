#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行棋前战术讲解（口语化直播术语）。
读取 TCHESS 的 /api/state，取引擎推荐着法，模拟走完后分析战术，输出主播口语。

战术识别（真实棋盘几何）：
  开局名：当头炮 / 仙人指路 / 飞相局 / 起马局 / 左炮巡河 / 过宫炮 / 仕角炮 ...
  走法口语：跳马 / 进车 / 平炮 / 拱卒 / 飞相 ...
  战术：将军 / 将杀 / 吃子 / 捉双 / 捉子 / 进车压马 /
        闪将 / 将军抽车 / 马后炮 / 重炮

坐标约定（与 TCHESS 引擎一致）：
  着法 "a0b0" = 源列(a-i) 源行(0-9) 目标列 目标行
  列：a->0..i->8；行：数字 0->9(红底线)..9->0(黑底线)
  board[10][9]，board[y][x]，y=0 顶(黑) ~ y=9 底(红)
  红大写 R N B A K C P，黑小写 r n b a k c p

用法：
  python tactic_commentator.py            # 一次
  python tactic_commentator.py --loop     # 每 3 秒轮询（直播用）
"""
import sys
import time
import requests

API = "http://127.0.0.1:8787/api/state"
PIECE_CN = {'K': '帅', 'A': '仕', 'B': '相', 'N': '马', 'R': '车', 'C': '炮', 'P': '兵',
            'k': '将', 'a': '士', 'b': '象', 'n': '马', 'r': '车', 'c': '炮', 'p': '卒'}
VALUE = {'R': 9, 'r': 9, 'C': 4.5, 'c': 4.5, 'N': 4, 'n': 4, 'B': 2.5, 'b': 2.5,
         'A': 2, 'a': 2, 'P': 1, 'p': 1, 'K': 1000, 'k': 1000}

# ---------------------------------------------------------------- 基础工具

def is_red(p): return p != ' ' and p.isupper()

def is_enemy(p, red_side): return p != ' ' and is_red(p) != red_side

def in_board(r, c): return 0 <= r <= 9 and 0 <= c <= 8

def find_king(board, red_side):
    k = 'K' if red_side else 'k'
    for r in range(10):
        for c in range(9):
            if board[r][c] == k:
                return r, c
    return None

def parse_move(move):
    fx, fy = ord(move[0]) - 97, 9 - int(move[1])
    tx, ty = ord(move[2]) - 97, 9 - int(move[3])
    return (fy, fx), (ty, tx)

def apply_move(board, move):
    (fy, fx), (ty, tx) = parse_move(move)
    b = [row[:] for row in board]
    captured = b[ty][tx]
    b[ty][tx] = b[fy][fx]
    b[fy][fx] = ' '
    return b, (fy, fx), (ty, tx), (captured if captured != ' ' else None)

def board_to_fen(board, red_to_move):
    """把走后棋盘转成 FEN（供记录新局面）。"""
    rows = []
    for r in range(10):
        s, empty = '', 0
        for c in range(9):
            p = board[r][c]
            if p == ' ':
                empty += 1
            else:
                if empty: s += str(empty); empty = 0
                s += p
        if empty: s += str(empty)
        rows.append(s)
    return '/'.join(rows) + (' w - - 0 1' if red_to_move else ' b - - 0 1')

def is_opening_position(state, board):
    """判断当前局面是否仍处于开局阶段（开局名只在开局报）。

    依据：双方棋子总数接近初始（>=26，初始为 32）+ 全回合数 <=8。
    棋子少了说明已进入中局换子，不再报"当头炮/飞相局"等开局名。
    """
    total = sum(1 for row in board for p in row if p != ' ')
    if total < 26:
        return False
    try:
        fullmove = int(state['fen'].split()[5])   # FEN 第 6 字段 = 全回合数
        if fullmove > 8:
            return False
    except Exception:
        pass
    return True

# ---------------------------------------------------------------- 攻击判定

def attacks(board, r, c):
    """该子能【吃】到的敌子位置集合（真实攻击）。"""
    p = board[r][c]
    if p == ' ':
        return set()
    res = set()
    red = is_red(p)

    def add(nr, nc):
        if in_board(nr, nc) and is_enemy(board[nr][nc], red):
            res.add((nr, nc))

    if p in 'Rr':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            while in_board(nr, nc):
                if board[nr][nc] == ' ':
                    nr, nc = nr + dr, nc + dc; continue
                if is_enemy(board[nr][nc], red): res.add((nr, nc))
                break
    elif p in 'Cc':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc, jumped = r + dr, c + dc, False
            while in_board(nr, nc):
                cell = board[nr][nc]
                if cell == ' ':
                    nr, nc = nr + dr, nc + dc; continue
                if not jumped:
                    jumped = True; nr, nc = nr + dr, nc + dc; continue
                if is_enemy(cell, red): res.add((nr, nc))
                break
    elif p in 'Nn':
        for dr, dc, br, bc in ((2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0),
                               (1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and board[r + br][c + bc] == ' ':
                add(nr, nc)
    elif p in 'Pp':
        fwd = -1 if red else 1
        add(r + fwd, c)
        crossed = (r < 5) if red else (r >= 5)
        if crossed:
            add(r, c + 1); add(r, c - 1)
    elif p in 'Bb':
        home = (lambda rr: rr >= 5) if red else (lambda rr: rr <= 4)
        for dr, dc in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and home(nr) and board[r + dr // 2][c + dc // 2] == ' ':
                add(nr, nc)
    elif p in 'Aa':
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add(nr, nc)
    elif p in 'Kk':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add(nr, nc)
    return res

def reach(board, r, c):
    """该子可到达/控制的所有格子（含空位、同方、敌方），用于保护(有根)判断。"""
    p = board[r][c]
    if p == ' ':
        return set()
    res = set()
    red = is_red(p)

    def add(nr, nc):
        if in_board(nr, nc):
            res.add((nr, nc))

    if p in 'Rr':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            while in_board(nr, nc):
                add(nr, nc)
                if board[nr][nc] != ' ':
                    break
                nr, nc = nr + dr, nc + dc
    elif p in 'Cc':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc, jumped = r + dr, c + dc, False
            while in_board(nr, nc):
                if board[nr][nc] == ' ':
                    add(nr, nc); nr, nc = nr + dr, nc + dc; continue
                if not jumped:
                    jumped = True; nr, nc = nr + dr, nc + dc; continue
                add(nr, nc); break
    elif p in 'Nn':
        for dr, dc, br, bc in ((2, 1, 1, 0), (2, -1, 1, 0), (-2, 1, -1, 0), (-2, -1, -1, 0),
                               (1, 2, 0, 1), (-1, 2, 0, 1), (1, -2, 0, -1), (-1, -2, 0, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and board[r + br][c + bc] == ' ':
                add(nr, nc)
    elif p in 'Pp':
        fwd = -1 if red else 1
        add(r + fwd, c)
        crossed = (r < 5) if red else (r >= 5)
        if crossed:
            add(r, c + 1); add(r, c - 1)
    elif p in 'Bb':
        home = (lambda rr: rr >= 5) if red else (lambda rr: rr <= 4)
        for dr, dc in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and home(nr) and board[r + dr // 2][c + dc // 2] == ' ':
                add(nr, nc)
    elif p in 'Aa':
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add(nr, nc)
    elif p in 'Kk':
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if in_board(nr, nc) and 3 <= nc <= 5 and (0 <= nr <= 2 if not red else 7 <= nr <= 9):
                add(nr, nc)
    return res

def is_protected(board, r, c, side_red):
    """位置 (r,c) 上的子是否被同方其它子保护（有根）。"""
    for rr in range(10):
        for cc in range(9):
            p = board[rr][cc]
            if p == ' ' or is_red(p) != side_red or (rr, cc) == (r, c):
                continue
            if (r, c) in reach(board, rr, cc):
                return True
    return False

def is_check(board, red_side):
    king = find_king(board, red_side)
    if not king:
        return False
    kr, kc = king
    for r in range(10):
        for c in range(9):
            if is_enemy(board[r][c], red_side) and (kr, kc) in attacks(board, r, c):
                return True
    for r in range(10):
        if board[r][kc] == ('k' if red_side else 'K'):
            lo, hi = min(r, kr), max(r, kr)
            if all(board[i][kc] == ' ' for i in range(lo + 1, hi)):
                return True
    return False

def check_sources(board, red_side):
    """返回所有正在攻击对方将的己方子位置。red_side 为将军方。"""
    king = find_king(board, not red_side)
    if not king:
        return []
    out = []
    for r in range(10):
        for c in range(9):
            if is_red(board[r][c]) == red_side and (king in attacks(board, r, c)):
                out.append((r, c))
    return out

def line_between(board, a, b):
    ar, ac, br, bc = a[0], a[1], b[0], b[1]
    if ar == br:
        lo, hi = sorted([ac, bc])
        return [board[ar][i] for i in range(lo + 1, hi) if board[ar][i] != ' ']
    if ac == bc:
        lo, hi = sorted([ar, br])
        return [board[i][ac] for i in range(lo + 1, hi) if board[i][ac] != ' ']
    return None

def cannon_screen(board, cannon_pos, king_pos):
    """炮攻击将时，线上的炮架子。"""
    between = line_between(board, cannon_pos, king_pos)
    if between and len(between) == 1:
        return between[0]
    return None

# ---------------------------------------------------------------- 走法口语

def move_verb(move_cn):
    """把中文着法转成口语走法，如 马三进五->跳马，车一平四->平车。"""
    piece = None
    for ch in move_cn:
        if ch in '马车炮兵卒相象士仕帅将':
            piece = ch; break
    if piece is None:
        return move_cn
    verb = '进' if '进' in move_cn else ('退' if '退' in move_cn else ('平' if '平' in move_cn else ''))
    style = {
        ('马', '进'): '跳马', ('马', '退'): '退马',
        ('车', '进'): '进车', ('车', '平'): '平车', ('车', '退'): '退车',
        ('炮', '进'): '进炮', ('炮', '平'): '平炮', ('炮', '退'): '退炮',
        ('兵', '进'): '进兵', ('卒', '进'): '拱卒', ('兵', '平'): '兵平', ('卒', '平'): '卒平',
        ('相', '进'): '飞相', ('象', '进'): '飞象',
        ('士', '进'): '支士', ('仕', '进'): '支仕',
        ('帅', '进'): '上帅', ('将', '进'): '上将',
    }
    return style.get((piece, verb), move_cn)

# ---------------------------------------------------------------- 战术分析

OPENINGS = {
    '炮二平五': '当头炮', '炮八平五': '当头炮',
    '兵三进一': '仙人指路', '兵七进一': '仙人指路',
    '相三进五': '飞相局', '相七进五': '飞相局',
    '马二进三': '起马局', '马八进七': '起马局',
    '炮八进二': '左炮巡河',
    '炮二平六': '过宫炮', '炮八平六': '过宫炮',
    '炮二平四': '仕角炮',
}

def analyze_tactics(after, frm, to, move_cn, mate, captured, is_opening=False):
    """在走完推荐着法后的局面上分析战术。返回 (口语走法, 开局名, 战术词列表)。"""
    piece = after[to[0]][to[1]]
    red = is_red(piece)
    atk = attacks(after, to[0], to[1])
    enemy_king = find_king(after, not red)
    tactics = []

    checked = is_check(after, not red)
    if checked:
        if mate:
            tactics.append('将杀')
        else:
            tactics.append('将军')
            sources = check_sources(after, red)
            moved_pos = to
            # 闪将：将军来源不是被移动子（被移动子让开，露出后方子将军）
            if moved_pos not in sources:
                tactics.append('闪将')
            # 马后炮 / 重炮：将军炮的炮架类型
            for (sr, sc) in sources:
                sp = after[sr][sc]
                if sp in 'Cc' and enemy_king:
                    screen = cannon_screen(after, (sr, sc), enemy_king)
                    if screen:
                        if screen.upper() == 'N':
                            tactics.append('马后炮')
                        elif screen.upper() == 'C':
                            tactics.append('重炮')
            # 将军抽车/抽子：闪开将军的同时，被移动子攻击对方高价值子
            if moved_pos not in sources and enemy_king:
                high = [(r, c) for (r, c) in atk if (r, c) != enemy_king and VALUE.get(after[r][c], 0) >= 4]
                if high:
                    target = after[high[0][0]][high[0][1]]
                    tactics.append('将军抽' + PIECE_CN.get(target, '子'))

    if captured and captured != ' ' and is_red(captured) != red:
        tactics.append('吃掉对方' + PIECE_CN.get(captured, '子'))

    capturable = [(r, c) for (r, c) in atk if not (enemy_king and (r, c) == enemy_king)]
    # 捉只针对无根子（有根子被攻叫兑/压制，不算捉）
    unrooted = [(r, c) for (r, c) in capturable if not is_protected(after, r, c, not red)]
    if len(unrooted) >= 2:
        tactics.append('捉双')
    elif len(unrooted) == 1:
        tactics.append('捉' + PIECE_CN.get(after[unrooted[0][0]][unrooted[0][1]], '子'))

    # 进车压马：车走后攻击范围压到对方马
    if piece in 'Rr' and any(after[r][c] in 'Nn' for (r, c) in capturable):
        tactics.append('进车压马')

    verb = move_verb(move_cn)
    opening = OPENINGS.get(move_cn) if is_opening else None
    return verb, opening, tactics


def comment(state):
    best = state['analysis']['best']
    if not best:
        return '引擎暂无分析，请先开启分析模式。'
    move = best['bestMove']
    move_cn = best['moveCn'].split()[0]
    board = state['board']
    side = state['sideToMove']
    red_move = (side == 'red')
    mate = best['mate']

    after, frm, to, captured = apply_move(board, move)
    opening_flag = is_opening_position(state, board)
    verb, opening, tactics = analyze_tactics(after, frm, to, move_cn, mate, captured, opening_flag)
    new_fen = board_to_fen(after, not red_move)

    side_txt = '红方' if red_move else '黑方'
    parts = [f'{side_txt}推荐：{move_cn}']
    if verb != move_cn:
        parts.append(f'（{verb}）')
    if opening:
        parts.append(f'，{opening}')
    if tactics:
        parts.append('，' + '、'.join(tactics))
    parts.append(f'。评估 {best["score"]}，深 {best["depth"]}')
    parts.append(f'  [新FEN {new_fen}]')
    return ''.join(parts)


def fetch():
    return requests.get(API, timeout=3).json()


def main():
    loop = '--loop' in sys.argv
    last = None
    while True:
        try:
            s = fetch()
            txt = comment(s)
            if txt != last:
                print(txt, flush=True)
                last = txt
        except Exception as e:
            print('请求失败:', e, flush=True)
        if not loop:
            break
        time.sleep(3)


if __name__ == '__main__':
    main()
