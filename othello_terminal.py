import os
import time
from dotenv import load_dotenv
from othello import OthelloGame
from rich.live import Live

## Configuration
load_dotenv()
GAME_EXPORT_DIR = os.getenv("GAME_EXPORT_DIR", "game_exports/")
TERMINAL_EXPORT_PREFIX = os.getenv("TERMINAL_EXPORT_PREFIX", "othello_terminal_data_")




if __name__ == "__main__":
    game = OthelloGame(use_rich_ui=True, use_file_logging=True)
    
    # Use 'Live' context manager to update the screen in place
    with Live(game.get_game_view(), refresh_per_second=4, screen=True) as live:
        
        while not game.game_over:
            # Update the UI
            live.update(game.get_game_view())
            
            # Artificial delay so humans can watch
            time.sleep(0.05)
            
            # Game Logic
            valid = game.get_valid_moves(game.board, game.turn)
            
            if not valid:
                game.play_next_auto()
            else:
                game.play_next_auto()
        
        # Final update to show Game Over state
        live.update(game.get_game_view())
        
        # Keep the final screen for 3 seconds before exiting
        time.sleep(3)

    print(f"Game finished. Winner: {game.winner}")
    

    # Export using the internal method which handles the full dataset
    if not os.path.exists(GAME_EXPORT_DIR):
        os.makedirs(GAME_EXPORT_DIR)
    full_path = os.path.join(GAME_EXPORT_DIR, f"{TERMINAL_EXPORT_PREFIX}{game.game_id}.csv")
    game.export_csv(full_path)