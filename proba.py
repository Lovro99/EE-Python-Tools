import tkinter as tk
from tkinter import simpledialog

class TextEditorCanvas:
    def __init__(self, root):
        self.root = root
        self.canvas = tk.Canvas(root, width=600, height=800, bg='lightgrey')
        self.canvas.pack()

        # Lista svih tekstova: svaki je dict {'text':..., 'x':..., 'y':...}
        self.texts = []
        self.fontsize = 22
        self.selected = None
        self.dragged = None
        self.offset = (0, 0)

        # UI kontrole
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Dodaj tekst", command=self.add_text).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Obriši tekst", command=self.remove_text_mode).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Pomak tekst", command=self.move_text_mode).pack(side="left", padx=4)

        self.mode = tk.StringVar(value='add')

        # početni mod: dodavanje
        self.canvas.bind("<Button-1>", self.canvas_click)
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)

        self.draw_all()

    def draw_all(self):
        self.canvas.delete("all")
        for t in self.texts:
            self.canvas.create_text(t['x'], t['y'], text=t['text'], fill='blue', font=("Arial", self.fontsize), tags='txt')
            if t == self.selected:
                self.canvas.create_rectangle(t['x']-30, t['y']-18, t['x']+30, t['y']+18, outline='red')

    def add_text(self):
        self.mode.set('add')
        text = simpledialog.askstring("Dodaj tekst", "Unesi tekst za prikaz:")
        if text:
            self.selected = {'text': text, 'x': 300, 'y': 100}
            self.texts.append(self.selected)
            self.draw_all()

    def remove_text_mode(self):
        self.mode.set('remove')

    def move_text_mode(self):
        self.mode.set('move')
    
    def canvas_click(self, event):
        print(f"Klik: {event.x}, {event.y}")
        for idx, t in enumerate(self.texts):
            print(f"Text {idx}: {t['x']}, {t['y']}, tekst={t['text']}")
        if self.mode.get() == 'remove':
            min_dist, nearest_idx = 9999, None
            for idx, t in enumerate(self.texts):
                dist = abs(event.x - t['x']) + abs(event.y - t['y'])
                if dist < min_dist:
                    min_dist, nearest_idx = dist, idx
            if min_dist < 50 and nearest_idx is not None:
                del self.texts[nearest_idx]
                self.draw_all()
        elif self.mode.get() == 'add' and self.selected is not None:
            self.selected['x'] = event.x
            self.selected['y'] = event.y
            self.selected = None
            self.draw_all()

    
    def canvas_press(self, event):
        if self.mode.get() == 'move':
            for t in self.texts:
                if abs(event.x-t['x']) < 30 and abs(event.y-t['y']) < 18:
                    self.dragged = t
                    self.offset = (event.x-t['x'], event.y-t['y'])
                    break

    def canvas_drag(self, event):
        if self.mode.get() == 'move' and self.dragged:
            self.dragged['x'] = event.x - self.offset[0]
            self.dragged['y'] = event.y - self.offset[1]
            self.draw_all()

    def canvas_release(self, event):
        self.dragged = None

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Pisanje, brisanje i pomak teksta")
    app = TextEditorCanvas(root)
    root.mainloop()
    
