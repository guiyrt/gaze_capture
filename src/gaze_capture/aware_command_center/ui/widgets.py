import tkinter as tk
from typing import Callable, Optional
from .theme import Theme

class HoldButton(tk.Canvas):
    """
    A custom Tkinter button that requires a long-press to activate.
    Displays a fill animation for visual feedback.
    """
    def __init__(
        self, 
        parent, 
        text: str, 
        command: Callable[[], None], 
        hold_time_ms: int = 1_000,
        bg_color: str = Theme.BG_INPUT,
        fill_color: str = Theme.DANGER,
        text_color: str = Theme.TEXT_MAIN,
        width: int = 150,
        height: int = 40
    ):
        super().__init__(
            parent, 
            width=width, 
            height=height, 
            bg=bg_color, 
            highlightthickness=0, 
            cursor="hand2"
        )
        self.command = command
        self.hold_time_ms = hold_time_ms
        self.bg_color = bg_color
        self.fill_color = fill_color
        self.text_color = text_color
        
        self.width = width
        self.height = height
        
        # State
        self._is_pressed = False
        self._progress = 0.0
        self._update_job: Optional[str] = None
        
        # Draw initial text
        self.text_id = self.create_text(
            self.width / 2, self.height / 2, 
            text=text, 
            font=Theme.FONT_BODY, 
            fill=self.text_color
        )
        self.fill_rect_id = self.create_rectangle(
            0, 0, 0, self.height, 
            fill=self.fill_color, 
            outline=""
        )
        # Ensure text stays on top of the fill animation
        self.tag_raise(self.text_id)

        # Bind events
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Leave>", self._on_release) # Cancel if mouse leaves bounds

    def _on_press(self, _):
        self._is_pressed = True
        self._progress = 0.0
        self._animate()

    def _on_release(self, _):
        self._is_pressed = False
        if self._update_job:
            self.after_cancel(self._update_job)
            self._update_job = None
            
        # Reset visual
        self._progress = 0.0
        self._update_visuals()

    def _animate(self):
        if not self._is_pressed:
            return
            
        # Step size assumes 50ms refresh rate (20 FPS)
        step = 50.0 / self.hold_time_ms
        self._progress += step
        
        if self._progress >= 1.0:
            self._progress = 1.0
            self._update_visuals()
            self._is_pressed = False # Prevent multiple triggers
            self.command() # Fire the action!
        else:
            self._update_visuals()
            self._update_job = self.after(50, self._animate)

    def _update_visuals(self):
        current_width = int(self.width * self._progress)
        self.coords(self.fill_rect_id, 0, 0, current_width, self.height)

    def set_state(self, state: str):
        """Allows enabling/disabling the button."""
        if state == "disabled":
            self.unbind("<ButtonPress-1>")
            self.config(cursor="arrow")
            self.itemconfig(self.text_id, fill=Theme.TEXT_MUTED)
        else:
            self.bind("<ButtonPress-1>", self._on_press)
            self.config(cursor="hand2")
            self.itemconfig(self.text_id, fill=self.text_color)