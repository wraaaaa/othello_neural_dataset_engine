"""Simple Othello game engine HTTP server.

This module provides a lightweight Flask-based API for an Othello/Reversi
engine used by the front-end UI in `templates/index.html`. It exposes routes
to query the board, make moves, undo, and reset the game. Utility functions
implement the core game logic (valid move detection, applying moves, scoring)
and small helpers to serialize internal state for JSON responses.
"""

from flask import Flask, render_template, jsonify, request
import time
import random  #
from enum import Enum

app = Flask(__name__)

BOARD_SIZE = 8

class Player(Enum):
    BLACK = "BLACK"
    WHITE = "WHITE"
    NONE = "NONE"
    """Enumeration of possible board cell states.

    - `BLACK` and `WHITE` represent player stones.
    - `NONE` represents an empty board cell.
    """

def create_initial_board():
    """Create and return the standard 8x8 Othello starting board.

    Returns:
        list[list[Player]]: A 2D list representing the initial board state.
    """
    board = [[Player.NONE for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    mid = BOARD_SIZE // 2
    board[mid-1][mid-1] = Player.WHITE
    board[mid][mid] = Player.WHITE
    board[mid-1][mid] = Player.BLACK
    board[mid][mid-1] = Player.BLACK
    return board

def get_scores(board):
    """Count stones for each player on the given `board`.

    Args:
        board (list[list[Player]]): The board to score.

    Returns:
        dict: A mapping with keys `black` and `white` and their counts.
    """
    b = sum(row.count(Player.BLACK) for row in board)
    w = sum(row.count(Player.WHITE) for row in board)
    return {"black": b, "white": w}

def get_valid_moves(board, player):
    """Compute all valid moves for `player` on `board`.

    Args:
        board (list[list[Player]]): Current board state.
        player (Player): The player whose moves to compute.

    Returns:
        list[list[int]]: List of `[row, col]` valid move coordinates.
    """
    moves = []
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if is_valid_move(board, r, c, player):
                moves.append([r, c])
    return moves

def is_valid_move(board, row, col, player):
    """Return True if placing `player` at (row, col) is a legal Othello move.

    The function checks all eight directions from the candidate cell looking
    for at least one contiguous line of opponent stones terminated by a
    friendly stone.

    Args:
        board (list[list[Player]]): Current board state.
        row (int): Row index for the candidate move.
        col (int): Column index for the candidate move.
        player (Player): The player making the move.

    Returns:
        bool: True if the move flips at least one opponent piece.
    """
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
    """Apply a move for `player` at `(row, col)` and return updated board.

    This function does not validate the move first; callers should ensure the
    move is legal (e.g., with `is_valid_move`). It returns both the new board
    and a list of coordinates that were flipped as a result of the move.

    Args:
        board (list[list[Player]]): Current board state.
        row (int): Row index where to place the stone.
        col (int): Column index where to place the stone.
        player (Player): Player making the move.

    Returns:
        tuple: `(new_board, flipped_coords)` where `new_board` is the updated
               2D board and `flipped_coords` is a list of `[r, c]` pairs.
    """
    new_board = [row[:] for row in board]
    new_board[row][col] = player
    opponent = Player.WHITE if player == Player.BLACK else Player.BLACK
    directions = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]
    
    flipped_coords = []
    for dr, dc in directions:
        r, c = row + dr, col + dc
        to_flip = []
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            if new_board[r][c] == opponent:
                to_flip.append([r, c])
            elif new_board[r][c] == player:
                for fr, fc in to_flip:
                    new_board[fr][fc] = player
                    flipped_coords.append([fr, fc])
                break
            else:
                break
            r += dr
            c += dc
    return new_board, flipped_coords


def serialize_board(board):
    """Convert board `Player` enum values into plain strings for JSON.

    Args:
        board (list[list[Player]]): Board to serialize.

    Returns:
        list[list[str]]: 2D list with string values 'BLACK', 'WHITE', or 'NONE'.
    """
    return [[cell.value for cell in row] for row in board]

def serialize_history(history):
    """Serialize stored move `history` to JSON-friendly dictionaries.

    Args:
        history (list[dict]): Internal history list where each entry stores
                              move metadata and a `boardBefore` snapshot.

    Returns:
        list[dict]: JSON-serializable history entries.
    """
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

# --- Global State ---
def get_initial_state():
    return {
        "board": create_initial_board(),
        "current_player": Player.BLACK,
        "history": [],
        "game_over": False,
        "last_move": None,
        "last_flipped": []
    }

game_state = get_initial_state()

# --- Core Game Logic Helper ---
def execute_move_logic(r, c):
    """Executes a move at (r, c) for the current player if valid.
    
    Returns:
        bool: True if move was executed, False if invalid or game over.
    """
    global game_state
    
    if game_state['game_over']:
        return False

    # Validation
    if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
        return False
        
    current_p = game_state['current_player']
    if not is_valid_move(game_state['board'], r, c, current_p):
        return False

    # Snapshot for history
    board_before = [row[:] for row in game_state['board']]
    
    # Apply the move
    new_board, flipped = apply_move(game_state['board'], r, c, current_p)
    
    # Update main state
    game_state['board'] = new_board
    game_state['last_move'] = [r, c]
    game_state['last_flipped'] = flipped

    # Determine next player and game status
    opponent = Player.WHITE if current_p == Player.BLACK else Player.BLACK
    opponent_moves = get_valid_moves(game_state['board'], opponent)
    
    # Record to history
    game_state['history'].append({
        "player": current_p,
        "row": r, "col": c,
        "timestamp": time.time(),
        "boardBefore": board_before,
        "scoreAfter": get_scores(game_state['board']),
        "nextMovesCount": len(opponent_moves),
        "last_move": [r, c],       
        "last_flipped": flipped    
    })

    # Turn management
    if opponent_moves:
        game_state['current_player'] = opponent
    else:
        # If opponent has no moves, check if current player has moves (double skip)
        if not get_valid_moves(game_state['board'], current_p):
            game_state['game_over'] = True
            
    return True

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/move', methods=['POST'])
def move():
    try:
        data = request.json or {}
        r, c = data.get('row', -99), data.get('col', -99)
        
        success = execute_move_logic(r, c)
        if not success:
            print(f"Invalid move attempted at {r}, {c}")

        return jsonify(get_response_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/bot-move', methods=['POST'])
def bot_move():
    """Calculates and executes a random valid move for the current player."""
    try:
        if game_state['game_over']:
             return jsonify(get_response_data())

        current_p = game_state['current_player']
        valid_moves = get_valid_moves(game_state['board'], current_p)
        
        if valid_moves:
            # AI LOGIC: Random Choice
            move = random.choice(valid_moves)
            execute_move_logic(move[0], move[1])
        
        return jsonify(get_response_data())
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

@app.route('/undo', methods=['POST'])
def undo():
    global game_state
    """Undo the last move and return the resulting game state.

    The undo operation restores the most recent history snapshot where
    possible; if no history remains the board is reset to the initial
    configuration.
    """
    if game_state['history']:
        game_state['history'].pop()
        if game_state['history']:
            prev = game_state['history'][-1]
            game_state['board'] = apply_move(prev['boardBefore'], prev['row'], prev['col'], prev['player'])[0]
            game_state['last_move'] = prev['last_move']
            game_state['last_flipped'] = prev['last_flipped']
            game_state['current_player'] = Player.WHITE if prev['player'] == Player.BLACK else Player.BLACK
            
            # Re-check turn logic in case of skips
            if not get_valid_moves(game_state['board'], game_state['current_player']):
                game_state['current_player'] = prev['player']
        else:
            game_state = get_initial_state()
        game_state['game_over'] = False
    return jsonify(get_response_data())

@app.route('/reset', methods=['POST'])
def reset():
    global game_state
    """Reset the server-side game state to the initial configuration.

    Returns the fresh state as JSON for immediate UI consumption.
    """
    print("Resetting Game Engine")
    game_state = get_initial_state()
    # After resetting, we return the fresh state directly to the UI
    return jsonify(get_response_data())

def get_response_data():
    """Build a JSON-serializable snapshot of the current game state."""
    return {
        "board": serialize_board(game_state['board']),
        "current_player": game_state['current_player'].value,
        "valid_moves": get_valid_moves(game_state['board'], game_state['current_player']),
        "history": serialize_history(game_state['history']),
        "scores": get_scores(game_state['board']),
        "game_over": game_state['game_over'],
        "last_move": game_state.get('last_move'),
        "last_flipped": game_state.get('last_flipped', [])
    }

if __name__ == '__main__':
    print("--- OTHELLO PRO SERVER ONLINE ---")
    print("Open: http://127.0.0.1:5001")
    app.run(debug=True, port=5001)