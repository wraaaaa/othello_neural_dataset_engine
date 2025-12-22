from flask import Flask, render_template, jsonify, request
import time
from enum import Enum

app = Flask(__name__)

BOARD_SIZE = 8

class Player(Enum):
    BLACK = "BLACK"
    WHITE = "WHITE"
    NONE = "NONE"

def create_initial_board():
    board = [[Player.NONE for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    mid = BOARD_SIZE // 2
    board[mid-1][mid-1] = Player.WHITE
    board[mid][mid] = Player.WHITE
    board[mid-1][mid] = Player.BLACK
    board[mid][mid-1] = Player.BLACK
    return board

def get_scores(board):
    b = sum(row.count(Player.BLACK) for row in board)
    w = sum(row.count(Player.WHITE) for row in board)
    return {"black": b, "white": w}

def get_valid_moves(board, player):
    moves = []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if is_valid_move(board, r, c, player):
                moves.append([r, c])
    return moves

def is_valid_move(board, row, col, player):
    if board[row][col] != Player.NONE:
        return False
    opponent = Player.WHITE if player == Player.BLACK else Player.BLACK
    directions = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]
    for dr, dc in directions:
        r, c = row + dr, col + dc
        found_opponent = False
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            if board[r][c] == opponent:
                found_opponent = True
            elif board[r][c] == player:
                if found_opponent:
                    return True
                break
            else:
                break
            r += dr
            c += dc
    return False

def apply_move(board, row, col, player):
    new_board = [row[:] for row in board]
    new_board[row][col] = player
    opponent = Player.WHITE if player == Player.BLACK else Player.BLACK
    directions = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]
    
    flipped_coords = [] # NEW: Track which pieces were flipped
    for dr, dc in directions:
        r, c = row + dr, col + dc
        to_flip = []
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            if new_board[r][c] == opponent:
                to_flip.append([r, c])
            elif new_board[r][c] == player:
                for fr, fc in to_flip:
                    new_board[fr][fc] = player
                    flipped_coords.append([fr, fc]) # Record the flip
                break
            else:
                break
            r += dr
            c += dc
    return new_board, flipped_coords


def serialize_board(board):
    return [[cell.value for cell in row] for row in board]

def serialize_history(history):
    return [
        {
            "player": move["player"].value,
            "row": move["row"],
            "col": move["col"],
            "timestamp": move["timestamp"],
            "boardBefore": serialize_board(move["boardBefore"]),
            "scoreAfter": move["scoreAfter"],
            "nextMovesCount": move.get("nextMovesCount", 0)
        }
        for move in history
    ]

game_state = {
    "board": create_initial_board(),
    "current_player": Player.BLACK,
    "history": [],
    "game_over": False,
    "last_move": None,      # NEW: [r, c]
    "last_flipped": []      # NEW: [[r, c], ...]
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def move():
    global game_state
    try:
        data = request.json or {}
        r, c = data.get('row', -99), data.get('col', -99)

        # 1. Check Bounds & Game Over Status
        if (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE) and not game_state['game_over']:
            
            # 2. NEW: Check if move is valid according to Othello rules
            if is_valid_move(game_state['board'], r, c, game_state['current_player']):
                
                board_before = [row[:] for row in game_state['board']]
                
                # Receive flipped coordinates
                new_board, flipped = apply_move(game_state['board'], r, c, game_state['current_player'])
                
                game_state['board'] = new_board
                game_state['last_move'] = [r, c]
                game_state['last_flipped'] = flipped

                opponent = Player.WHITE if game_state['current_player'] == Player.BLACK else Player.BLACK
                opponent_moves = get_valid_moves(game_state['board'], opponent)
                
                game_state['history'].append({
                    "player": game_state['current_player'],
                    "row": r, "col": c,
                    "timestamp": time.time(),
                    "boardBefore": board_before,
                    "scoreAfter": get_scores(game_state['board']),
                    "nextMovesCount": len(opponent_moves),
                    "last_move": [r, c],       
                    "last_flipped": flipped    
                })

                if opponent_moves:
                    game_state['current_player'] = opponent
                else:
                    if not get_valid_moves(game_state['board'], game_state['current_player']):
                        game_state['game_over'] = True
            
            # log an "Invalid Move Attempt"
            else:
                print(f"Invalid move attempted at {r}, {c}")

        return jsonify(get_response_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/undo', methods=['POST'])
def undo():
    global game_state
    if game_state['history']:
        game_state['history'].pop()
        if game_state['history']:
            prev = game_state['history'][-1]
            # Since boardBefore is a snapshot of the board BEFORE that move,
            # we must reconstruct the board state. Simplest is to just reset 
            # highlights or restore from history properly.
            game_state['board'] = apply_move(prev['boardBefore'], prev['row'], prev['col'], prev['player'])[0]
            game_state['last_move'] = prev['last_move']
            game_state['last_flipped'] = prev['last_flipped']
            game_state['current_player'] = Player.WHITE if prev['player'] == Player.BLACK else Player.BLACK
            # Check if current player actually has moves, otherwise it would have stayed on prev player
            if not get_valid_moves(game_state['board'], game_state['current_player']):
                game_state['current_player'] = prev['player']
        else:
            game_state['board'] = create_initial_board()
            game_state['last_move'] = None
            game_state['last_flipped'] = []
            game_state['current_player'] = Player.BLACK
        game_state['game_over'] = False
    return jsonify(get_response_data())

def get_response_data():
    return {
        "board": serialize_board(game_state['board']),
        "current_player": game_state['current_player'].value,
        "valid_moves": get_valid_moves(game_state['board'], game_state['current_player']),
        "history": serialize_history(game_state['history']),
        "scores": get_scores(game_state['board']),
        "game_over": game_state['game_over'],
        "last_move": game_state['last_move'],
        "last_flipped": game_state['last_flipped']
    }

# --- Updated Global State Initialization ---
def get_initial_state():
    return {
        "board": create_initial_board(),
        "current_player": Player.BLACK,
        "history": [],
        "game_over": False,
        "last_move": None,      # Ensure this is explicitly initialized
        "last_flipped": []      # Ensure this is explicitly initialized
    }

game_state = get_initial_state()

# --- Updated Reset Route ---
@app.route('/reset', methods=['POST'])
def reset():
    global game_state
    print("Resetting Game Engine")
    game_state = get_initial_state()
    # After resetting, we return the fresh state directly to the UI
    return jsonify(get_response_data())

# --- Updated Response Helper ---
def get_response_data():
    return {
        "board": serialize_board(game_state['board']),
        "current_player": game_state['current_player'].value,
        "valid_moves": get_valid_moves(game_state['board'], game_state['current_player']),
        "history": serialize_history(game_state['history']),
        "scores": get_scores(game_state['board']),
        "game_over": game_state['game_over'],
        "last_move": game_state.get('last_move'), # Use .get() for safety
        "last_flipped": game_state.get('last_flipped', []) # Use .get() for safety
    }


if __name__ == '__main__':
    print("--- OTHELLO PRO SERVER ONLINE ---")
    print("Open: http://127.0.0.1:5001")
    app.run(debug=True, port=5001)