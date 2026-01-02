import numpy as np
import logging
import random
import time
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Tuple
from dotenv import load_dotenv

# --- Rich UI Imports ---
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich import box


# --- Configuration ---
load_dotenv()

LOG_FILE = os.getenv("LOG_FILENAME", "othello_game.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class OthelloGame:
    def __init__(self, use_rich_ui: bool = True, use_file_logging: bool = True):
        # 0. Identify the game univocally
        self.game_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.use_rich_ui = use_rich_ui
        self.use_file_logging = use_file_logging
        
        self.SIZE = 8
        
        # Static Zones
        self.CORNERS = {(0,0), (0,7), (7,0), (7,7)}
        self.X_SQUARES = {(1,1), (1,6), (6,1), (6,6)}
        self.C_SQUARES = {(0,1), (1,0), (0,6), (1,7), (6,0), (7,1), (6,7), (7,6)}
        self.SEMI_CORNERS = {(2,2), (2,5), (5,2), (5,5)}
        
        # UI State
        self.log_buffer = [] 
        self.max_log_lines = 8
        
        self.reset_board()

    def reset_board(self):
        self.board = np.zeros((self.SIZE, self.SIZE), dtype=np.int8)
        self.stability = np.zeros((self.SIZE, self.SIZE), dtype=np.int32)
        
        # Standard Setup
        self.board[3, 3] = 1
        self.board[4, 4] = 1
        self.board[3, 4] = -1
        self.board[4, 3] = -1
        
        self.turn = -1 
        self.history = []
        self.winner = 0
        self.game_over = False
        self.last_move_coords = None
        self.last_flipped_coords = []
        self._log(f"Game Reset. ID: {self.game_id}")

    def _log(self, message: str):
        if self.use_file_logging: logging.info(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_buffer.append(f"[{timestamp}] {message}")
        if len(self.log_buffer) > self.max_log_lines: self.log_buffer.pop(0)

    def _is_on_board(self, x: int, y: int) -> bool:
        return 0 <= x < self.SIZE and 0 <= y < self.SIZE

    def get_valid_moves(self, board_state: np.ndarray = None, player: int = None) -> Dict[Tuple[int, int], List[Tuple[int, int]]]:
        if board_state is None: board_state = self.board
        if player is None: player = self.turn
            
        valid_moves = {}
        opponent = -player
        
        rows, cols = np.where(board_state == 0)
        empty_cells = list(zip(rows.tolist(), cols.tolist()))
        
        directions = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

        for r, c in empty_cells:
            all_flips = []
            for dr, dc in directions:
                flips = []
                cr, cc = r + dr, c + dc
                while self._is_on_board(cr, cc) and board_state[cr, cc] == opponent:
                    flips.append((int(cr), int(cc)))
                    cr += dr
                    cc += dc
                if self._is_on_board(cr, cc) and board_state[cr, cc] == player and len(flips) > 0:
                    all_flips.extend(flips)
            
            if all_flips:
                valid_moves[(int(r), int(c))] = all_flips
        return valid_moves

    def calculate_score(self) -> Dict[str, int]:
        unique, counts = np.unique(self.board, return_counts=True)
        counts_dict = dict(zip(unique, counts))
        return {'black': int(counts_dict.get(-1, 0)), 'white': int(counts_dict.get(1, 0))}

    def apply_move(self, r: int, c: int) -> bool:
        if self.game_over: return False

        # Get valid moves (Metrics: Mobility Pre)
        valid_moves = self.get_valid_moves(self.board, self.turn)
        if (r, c) not in valid_moves:
            return False

        flips = valid_moves[(r, c)]
        
        # --- 1. Gather Metrics (Pre-Move) ---
        score_pre = self.calculate_score()
        mobility_pre = len(valid_moves)

        # Positional flags
        is_corner = (r, c) in self.CORNERS
        is_semi = (r, c) in self.SEMI_CORNERS
        is_x = (r, c) in self.X_SQUARES
        is_c = (r, c) in self.C_SQUARES
        is_border = (r == 0 or r == 7 or c == 0 or c == 7) and not is_corner
        
        # Snapshot for History (Training Data)
        snapshot = {
            # Metadata
            'game_id': self.game_id,
            'game_turn_idx': len(self.history),
            'player': int(self.turn),
            'move_r': int(r), 
            'move_c': int(c),
            
            # Positional Features
            'is_corner': bool(is_corner),
            'is_border': bool(is_border),
            'is_semi': bool(is_semi),
            'is_x_square': bool(is_x),
            'is_c_square': bool(is_c),
            
            # Impact Features (Pre)
            'score_pre_b': score_pre['black'],
            'score_pre_w': score_pre['white'],
            'mobility_pre': mobility_pre,
            'cells_changed': len(flips) + 1,
            
            # State Features (Flattened for CSV)
            'board_state': self.board.flatten().tolist(),
            'stability_state': self.stability.flatten().tolist(),
            
            # Undo / UI Restore Data
            'board_copy': self.board.copy(),
            'stability_copy': self.stability.copy(),
            'turn_copy': self.turn,
            'last_move_coords': self.last_move_coords,
            'last_flipped_coords': self.last_flipped_coords,
            'player_color': "BLACK" if self.turn == -1 else "WHITE"
        }
        
        # --- 2. Update Board ---
        self.board[r, c] = self.turn
        for fr, fc in flips:
            self.board[fr, fc] = self.turn
            
        # --- 3. Update Stability ---
        self.stability += 1
        self.stability[r, c] = 0
        for fr, fc in flips:
            self.stability[fr, fc] = 0
            
        self.last_move_coords = [int(r), int(c)]
        self.last_flipped_coords = [[int(f[0]), int(f[1])] for f in flips]

        # --- 4. Post-Move Metrics ---
        score_post = self.calculate_score()
        foe_moves = self.get_valid_moves(self.board, -self.turn)
        mobility_foe_after = len(foe_moves)
        forced_pass = (mobility_foe_after == 0)
        
        # Enrich snapshot with Post-Move data
        snapshot['score_post_b'] = score_post['black']
        snapshot['score_post_w'] = score_post['white']
        snapshot['mobility_foe_after'] = mobility_foe_after
        snapshot['forced_pass'] = forced_pass
        snapshot['score_post'] = score_post # For UI
        
        self.history.append(snapshot)
        
        # UI Log
        p_name = "Black" if self.turn == -1 else "White"
        self._log(f"{p_name} plays [{r},{c}]. Flips: {len(flips)}")

        # --- 5. Turn Logic ---
        if not foe_moves:
            # Check if WE (current player) also have no moves -> Game Over
            if not self.get_valid_moves(self.board, self.turn):
                self.game_over = True
                self._determine_winner()
            else:
                self._log(f"Player {self.turn} passes.")
                pass 
        else:
            self.turn = -self.turn
            
        return True

    def undo(self):
        if not self.history: return False
        last_state = self.history.pop()
        
        # Restore Logic
        self.board = last_state['board_copy']
        self.stability = last_state['stability_copy']
        self.turn = last_state['turn_copy']
        self.last_move_coords = last_state['last_move_coords']
        self.last_flipped_coords = last_state['last_flipped_coords']
        self.game_over = False
        self.winner = 0
        return True

    def play_next_auto(self):
        """Auto-plays a single move or handles passing."""
        valid_moves = self.get_valid_moves()
        
        if not valid_moves:
            foe_moves = self.get_valid_moves(self.board, -self.turn)
            if not foe_moves:
                self.game_over = True
                self._determine_winner()
            else:
                self._log(f"Player {self.turn} passes.")
                self.turn = -self.turn
            return

        move = random.choice(list(valid_moves.keys()))
        self.apply_move(move[0], move[1])

    def _determine_winner(self):
        s = self.calculate_score()
        if s['black'] > s['white']: self.winner = -1
        elif s['white'] > s['black']: self.winner = 1
        else: self.winner = 0
        
        # Backfill winner into history (Important for training data)
        for record in self.history:
            record['game_winner'] = self.winner
            
        self._log(f"Game Over. Winner: {self.winner} (B:{s['black']} W:{s['white']})")

    def export_csv(self, filename: str):
        """Exports the rich history to a CSV file suitable for ML training."""
        if not self.history:
            return
        
        # Ensure the export directory exists if a path is provided in filename
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        df = pd.DataFrame(self.history)
        # Drop UI-specific objects
        cols_to_drop = ['board_copy', 'stability_copy', 'turn_copy', 'last_move_coords', 'last_flipped_coords']
        df_clean = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
        
        df_clean.to_csv(filename, index=False)
        self._log(f"History exported to {filename}")

    # --- Rich UI Rendering ---

    def get_game_view(self) -> Layout:
        """Returns a Rich Layout object representing the entire game interface."""
        
        # 1. The Board Table
        board_table = Table(box=box.ROUNDED, show_header=False, show_edge=True, pad_edge=False, padding=0)
        
        # Create columns (0-7)
        for _ in range(self.SIZE + 1):
            board_table.add_column(justify="center", width=4)

        # Header Row
        cols = [Text(" ")] + [Text(str(i), style="dim") for i in range(self.SIZE)]
        board_table.add_row(*cols)

        valid_moves = self.get_valid_moves(self.board, self.turn)
        valid_coords = set(valid_moves.keys())

        for r in range(self.SIZE):
            cells = [Text(str(r), style="dim")]
            for c in range(self.SIZE):
                val = self.board[r, c]
                if val == -1:
                    # Black piece
                    cells.append(Text("●", style="red bold"))
                elif val == 1:
                    # White piece
                    cells.append(Text("●", style="cyan bold"))
                elif (r, c) in valid_coords:
                    # Valid move
                    cells.append(Text("·", style="green"))
                else:
                    # Empty
                    cells.append(Text(" "))
            board_table.add_row(*cells)

        # 2. Statistics Panel
        scores = self.calculate_score()
        turn_text = "Black (-1)" if self.turn == -1 else "White (1)"
        turn_color = "red" if self.turn == -1 else "cyan"
        
        stats_content = Text()
        stats_content.append(f"Turn: ", style="bold")
        stats_content.append(f"{turn_text}\n", style=f"bold {turn_color}")
        stats_content.append("-" * 20 + "\n", style="dim")
        stats_content.append(f"Black Score: {scores['black']}\n", style="red")
        stats_content.append(f"White Score: {scores['white']}\n", style="cyan")
        stats_content.append("-" * 20 + "\n", style="dim")
        stats_content.append(f"Valid Moves: {len(valid_moves)}\n")
        stats_content.append(f"Move Count:  {len(self.history)}\n")
        stats_content.append(f"Game ID:\n{self.game_id}", style="dim")

        # 3. Log Panel
        log_text = Text()
        for line in self.log_buffer:
            log_text.append(line + "\n", style="white")

        # Layout Assembly
        layout = Layout()
        layout.split_row(
            Layout(Panel(Align.center(board_table), title="Othello Board", border_style="blue"), ratio=2),
            Layout(ratio=1, name="sidebar")
        )
        
        layout["sidebar"].split_column(
            Layout(Panel(stats_content, title="Statistics", border_style="green"), ratio=1),
            Layout(Panel(log_text, title="Game Log", border_style="yellow"), ratio=1)
        )

        return layout

    def get_state_snapshot(self) -> dict:
        """Returns a JSON-safe dict of the state."""
        board_str = []
        for row in self.board:
            r_str = []
            for cell in row:
                if cell == -1: r_str.append("BLACK")
                elif cell == 1: r_str.append("WHITE")
                else: r_str.append("NONE")
            board_str.append(r_str)
            
        ui_history = []
        for h in self.history:
            ui_history.append({
                "player": h['player_color'],
                "row": h['move_r'],
                "col": h['move_c'],
                "scoreAfter": h['score_post'],
                "nextMovesCount": h['mobility_foe_after']
            })

        valid_moves_clean = []
        for r, c in self.get_valid_moves().keys():
            valid_moves_clean.append([int(r), int(c)])

        return {
            "board": board_str,
            "current_player": "BLACK" if self.turn == -1 else "WHITE",
            "valid_moves": valid_moves_clean,
            "scores": self.calculate_score(),
            "history": ui_history,
            "game_over": bool(self.game_over),
            "last_move": self.last_move_coords,
            "last_flipped": self.last_flipped_coords
        }

