import os
import io
import csv
import uuid
import pandas as pd # Needed for the dataframe export logic
from flask import Flask, render_template, jsonify, request, Response, session
from othello import OthelloGame
from dotenv import load_dotenv


# Load environment variables
load_dotenv()
GAME_EXPORT_DIR = os.getenv("GAME_EXPORT_DIR", "game_exports/")
WEB_EXPORT_PREFIX = os.getenv("WEB_EXPORT_PREFIX", "othello_web_game_")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"


app = Flask(__name__)
# In production, use a static key to prevent sessions invalidating on restart
app.secret_key = os.urandom(24) 


# Global dictionary to store independent game sessions
# Structure: { 'user_uuid': OthelloGameInstance }
GAMES = {}

def get_user_game():
    """
    Retrieves the OthelloGame instance for the current user.
    If the user has no session or no game, creates one.
    """
    # 1. Ensure user has a Session ID
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']

    # 2. Check if this user already has a running game
    if user_id not in GAMES:
        print(f"Creating new game instance for user: {user_id}")
        GAMES[user_id] = OthelloGame(use_rich_ui=False, use_file_logging=False)
    
    return GAMES[user_id]

def check_and_export_if_game_over(game):
    """Checks if game ended, if so, saves CSV to server disk."""
    if game.game_over:
        # 2. Get Directory and Prefix from .env
        
        # 3. Create directory if it doesn't exist
        if not os.path.exists(GAME_EXPORT_DIR):
            os.makedirs(GAME_EXPORT_DIR)

        # 4. Construct full path
        filename = f"{WEB_EXPORT_PREFIX}{game.game_id}.csv"
        full_path = os.path.join(GAME_EXPORT_DIR, filename)

        print(f"Game Over. Auto-exporting to {full_path}...")
        game.export_csv(full_path)


@app.route("/")
def index():
    # Just render the template. The game is created when the frontend 
    # makes its first API call (usually the initial render call).
    return render_template("index.html")

@app.route("/move", methods=["POST"])
def move():
    try:
        game = get_user_game() 
        data = request.json or {}
        r, c = data.get("row"), data.get("col")
        
        # -1, -1 is often sent by the frontend just to fetch state
        if r is not None and c is not None and r != -1 and c != -1:
            game.apply_move(r, c)
            check_and_export_if_game_over(game)
            
        return jsonify(game.get_state_snapshot())
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/bot-move", methods=["POST"])
def bot_move():
    try:
        game = get_user_game() 
        game.play_next_auto()
        check_and_export_if_game_over(game)
        return jsonify(game.get_state_snapshot())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/undo", methods=["POST"])
def undo():
    try:
        game = get_user_game() 
        game.undo()
        return jsonify(game.get_state_snapshot())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/reset", methods=["POST"])
def reset():
    try:
        # We don't delete the instance, we just reset its board
        game = get_user_game() 
        game.reset_board()
        return jsonify(game.get_state_snapshot())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/export", methods=["GET"])
def export():
    """Generates a CSV of the current game history and triggers download."""
    try:
        game = get_user_game() 
        
        if not game.history:
            return "No moves to export", 400

        # Create DataFrame from history using the exact same logic as othello.py
        # to ensure ALL fields (new and old) are present.
        df = pd.DataFrame(game.history)
        
        # Drop UI-specific objects that shouldn't be in CSV
        cols_to_drop = ['board_copy', 'stability_copy', 'turn_copy', 'last_move_coords', 'last_flipped_coords', 'score_post']
        df_clean = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
        
        # Convert to CSV string
        output = df_clean.to_csv(index=False)
        
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=othello_web_export_{game.game_id}.csv"}
        )
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    print("--- OTHELLO WEB ENGINE STARTED ---")
    print(f"Open http://127.0.0.1:{FLASK_PORT} in your browser")
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)