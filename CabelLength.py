import networkx as nx
import matplotlib.pyplot as plt
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import math
import numpy as np

class DistributionCabinet:
    """Razdelni ormar sa fiksnom pozicijom"""
    def __init__(self, cabinet_id=0, x=0, y=0):
        self.id = cabinet_id
        self.x = x
        self.y = y
        self.position = (x, y)
    
    def __repr__(self):
        return f"Cabinet(id={self.id}, x={self.x}, y={self.y})"

class CablePlannerMST:
    def __init__(self, nodes_df, edges_df, cabinet=None, metric="manhattan"):
        """
        Inicijalizacija Cable Plannera

        Args:
            nodes_df: DataFrame sa stupcima [id, circuit_label, x, y]
            edges_df: DataFrame sa stupcima [from_node, to_node]
            cabinet: DistributionCabinet objekat (ako None, koristi default)
            metric: 'manhattan' (default) – kabeli se u zgradi vode
                    pravokutno (uz zidove/kanale), pa je L1 udaljenost
                    realnija procjena od zračne linije; 'euclidean' za
                    direktnu (zračnu) udaljenost.
        """
        self.nodes_data = nodes_df
        self.edges_data = edges_df
        self.metric = metric
        self.cabinet = cabinet if cabinet else DistributionCabinet(0, 0, 0)
        self.circuits = {}
        self.graphs = {}
        self.mst_results = {}
        self.colors = self._generate_colors()
        self._group_by_circuit()
        self._build_circuit_graphs()
    
    def _group_by_circuit(self):
        """Grupiraj čvorove po strujnim krugovima"""
        for circuit_label in self.nodes_data['circuit_label'].unique():
            circuit_data = self.nodes_data[self.nodes_data['circuit_label'] == circuit_label]
            nodes = {}
            for _, row in circuit_data.iterrows():
                nodes[row['id']] = {
                    'id': row['id'],
                    'x': row['x'],
                    'y': row['y'],
                    'circuit': circuit_label
                }
            self.circuits[circuit_label] = nodes
    
    def _generate_colors(self):
        """Generiši boje za svaki strujni krug"""
        colors = {}
        circuit_labels = self.nodes_data['circuit_label'].unique()
        color_palette = plt.cm.tab20(np.linspace(0, 1, max(20, len(circuit_labels))))
        for i, label in enumerate(circuit_labels):
            colors[label] = color_palette[i % len(color_palette)]
        return colors
    
    def _calculate_distance(self, node1, node2):
        """Udaljenost između dva čvora (u cm) prema self.metric"""
        if hasattr(node1, 'x'):
            x1, y1 = node1.x, node1.y
        else:
            x1, y1 = node1['x'], node1['y']

        if hasattr(node2, 'x'):
            x2, y2 = node2.x, node2.y
        else:
            x2, y2 = node2['x'], node2['y']

        dx = x1 - x2
        dy = y1 - y2
        if self.metric == "manhattan":
            return abs(dx) + abs(dy)
        return math.sqrt(dx**2 + dy**2)
    
    def _build_circuit_graphs(self):
        """Napravi grafove za sve strujne krugove sa stvarnim vezama"""
        for circuit_label, nodes in self.circuits.items():
            G = nx.Graph()
            cabinet_node = f"Cabinet_{circuit_label}"
            
            # Dodaj razdelni ormar
            G.add_node(cabinet_node, 
                      x=self.cabinet.x, 
                      y=self.cabinet.y, 
                      node_type='cabinet')
            
            # Dodaj sve čvorove kruga
            for node_id, node_data in nodes.items():
                G.add_node(node_id, 
                          x=node_data['x'], 
                          y=node_data['y'], 
                          node_type='regular')
            
            # Dodaj veze prema CSV-u (edges_data)
            for _, edge_row in self.edges_data.iterrows():
                from_node = edge_row['from_node']
                to_node = edge_row['to_node']
                
                # Provjeri da li su oba čvora u ovom krugu
                if from_node in nodes and to_node in nodes:
                    distance = self._calculate_distance(nodes[from_node], nodes[to_node])
                    G.add_edge(from_node, to_node, weight=distance, distance_cm=distance)
                
                # Veza od razdelnog ormara do čvora
                if from_node == "CABINET" and to_node in nodes:
                    distance = self._calculate_distance(self.cabinet, nodes[to_node])
                    G.add_edge(cabinet_node, to_node, weight=distance, distance_cm=distance)
                
                if to_node == "CABINET" and from_node in nodes:
                    distance = self._calculate_distance(self.cabinet, nodes[from_node])
                    G.add_edge(cabinet_node, from_node, weight=distance, distance_cm=distance)
            
            self.graphs[circuit_label] = G
    
    def calculate_mst(self):
        """Izračunaj MST za sve strujne krugove"""
        for circuit_label, G in self.graphs.items():
            # Izračunaj MST
            mst = nx.minimum_spanning_tree(G, weight='weight', algorithm='kruskal')
            
            # Izračunaj ukupnu duljinu
            total_length_cm = sum(data['weight'] for _, _, data in mst.edges(data=True))
            total_length_m = total_length_cm / 100
            
            # Spremi rezultate
            self.mst_results[circuit_label] = {
                'graph': G,
                'mst': mst,
                'total_length_cm': total_length_cm,
                'total_length_m': total_length_m,
                'edges_count': mst.number_of_edges(),
                'nodes_count': mst.number_of_nodes()
            }
    
    def get_summary_text(self):
        """Vrati sažetak kao text"""
        text = "="*70 + "\n"
        text += "SAŽETAK REZULTATA - MINIMALNO RAZAPINJUĆE STABLO\n"
        text += "="*70 + "\n\n"
        
        total_cable = 0
        for circuit_label, result in self.mst_results.items():
            text += f"📍 Strujni krug: {circuit_label}\n"
            text += f"   ├─ Duljina kabela: {result['total_length_m']:.2f} m\n"
            text += f"   ├─ Čvorovi: {result['nodes_count']}\n"
            text += f"   └─ Grane: {result['edges_count']}\n\n"
            
            total_cable += result['total_length_m']
            
            # Ispiši detalje grana
            text += f"   Kabelske veze (MST):\n"
            mst = result['mst']
            for i, (node1, node2, data) in enumerate(mst.edges(data=True), 1):
                length_m = data['weight'] / 100
                text += f"      {i:2}. {str(node1):20} ═══ {str(node2):20} : {length_m:8.2f} m\n"
            text += "\n"
        
        text += "="*70 + "\n"
        text += f"UKUPNA DULJINA KABELA ZA SVE KRUGOVE: {total_cable:.2f} m\n"
        text += "="*70 + "\n"
        
        return text
    
    def draw_circuit(self, ax, circuit_label):
        """Nacrtaj jedan strujni krug na danom ax-u"""
        result = self.mst_results[circuit_label]
        mst = result['mst']
        G = result['graph']
        color = self.colors[circuit_label]
        
        # Pripremi pozicije čvorova
        pos = {}
        for node in G.nodes():
            x = G.nodes[node].get('x', 0)
            y = G.nodes[node].get('y', 0)
            pos[node] = (x, y)
        
        # Nacrtaj sve čvorove
        cabinet_nodes = [n for n in G.nodes() if G.nodes[n].get('node_type') == 'cabinet']
        regular_nodes = [n for n in G.nodes() if G.nodes[n].get('node_type') != 'cabinet']
        
        # Nacrtaj sve grane iz originalnog grafa (sive, tanke, isprekidane)
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color='lightgray', 
                               width=0.5, alpha=0.2, style='dotted')
        
        # Nacrtaj MST grane sa posebnom bojom (debele, vidljive)
        mst_edges = list(mst.edges())
        edge_colors = []
        for u, v in mst_edges:
            # Ako je veza sa ormarem, crvena
            if "Cabinet" in str(u) or "Cabinet" in str(v):
                edge_colors.append('red')
            else:
                edge_colors.append(color)
        
        nx.draw_networkx_edges(mst, pos, ax=ax,
                               edge_color=edge_colors, width=2.5, alpha=0.9)
        
        # Nacrtaj razdelni ormar (poseban čvor)
        nx.draw_networkx_nodes(G, pos, nodelist=cabinet_nodes, ax=ax,
                              node_color='red', node_size=800, node_shape='s',
                              edgecolors='darkred', linewidths=2)
        
        # Nacrtaj obične čvorove
        nx.draw_networkx_nodes(G, pos, nodelist=regular_nodes, ax=ax,
                              node_color=[color], node_size=300, 
                              alpha=0.9, edgecolors='black', linewidths=1)
        
        # Dodaj labele
        labels = {}
        for n in G.nodes():
            if "Cabinet" in str(n):
                labels[n] = "C"
            else:
                labels[n] = str(n)
        
        nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=8, font_weight='bold')
        
        # Naslov i info
        title = f"{circuit_label}\n"
        title += f"Duljina: {result['total_length_m']:.2f} m | "
        title += f"Čvorovi: {result['nodes_count']} | Grane: {result['edges_count']}"
        
        ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        ax.axis('off')

class CablePlannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🔌 Kabliranje - Minimalno Razapinjuće Stablo")
        self.root.geometry("1600x900")
        
        # Kreiraj i učitaj podatke
        self.nodes_df, self.edges_df = self.create_test_database()
        self.cabinet = DistributionCabinet(0, 0, 0)
        self.planer = CablePlannerMST(self.nodes_df, self.edges_df, self.cabinet)
        self.planer.calculate_mst()
        
        # Kreiraj GUI
        self.setup_gui()
    
    def create_test_database(self):
        """Kreiraj test bazu sa većim koordinatama"""
        nodes_data = [
            # Krug 1: Parter - VELIKE KOORDINATE
            (1, 'Krug 1 - Parter', 423, 234),
            (2, 'Krug 1 - Parter', 1234, 456),
            (3, 'Krug 1 - Parter', 2145, 678),
            (4, 'Krug 1 - Parter', 1789, 1234),
            (5, 'Krug 1 - Parter', 2987, 1456),
            (6, 'Krug 1 - Parter', 567, 2145),
            (7, 'Krug 1 - Parter', 2345, 2567),
            (8, 'Krug 1 - Parter', 3456, 789),
            
            # Krug 2: Prvi kat
            (9, 'Krug 2 - Prvi kat', 4567, 1234),
            (10, 'Krug 2 - Prvi kat', 5678, 890),
            (11, 'Krug 2 - Prvi kat', 6789, 1567),
            (12, 'Krug 2 - Prvi kat', 5123, 2345),
            (13, 'Krug 2 - Prvi kat', 7234, 2678),
            (14, 'Krug 2 - Prvi kat', 6123, 3456),
            (15, 'Krug 2 - Prvi kat', 7890, 1123),
            
            # Krug 3: Drugi kat
            (16, 'Krug 3 - Drugi kat', 1567, 5123),
            (17, 'Krug 3 - Drugi kat', 2456, 4789),
            (18, 'Krug 3 - Drugi kat', 3456, 5678),
            (19, 'Krug 3 - Drugi kat', 2345, 6789),
            (20, 'Krug 3 - Drugi kat', 4123, 7234),
            (21, 'Krug 3 - Drugi kat', 1234, 6123),
            
            # Krug 4: Skladište
            (22, 'Krug 4 - Skladište', 7456, 5123),
            (23, 'Krug 4 - Skladište', 8567, 5678),
            (24, 'Krug 4 - Skladište', 8123, 6789),
            (25, 'Krug 4 - Skladište', 9234, 4789),
            (26, 'Krug 4 - Skladište', 9876, 6234),
            
            # Krug 5: Nova zona
            (27, 'Krug 5 - Nova zona', 3789, 3456),
            (28, 'Krug 5 - Nova zona', 4234, 4123),
            (29, 'Krug 5 - Nova zona', 5456, 3789),
            (30, 'Krug 5 - Nova zona', 4890, 5123),
        ]
        
        edges_data = [
            # Krug 1
            ('CABINET', 1),
            (1, 2),
            (1, 6),
            (2, 3),
            (3, 4),
            (3, 5),
            (4, 7),
            (5, 8),
            
            # Krug 2
            ('CABINET', 9),
            (9, 10),
            (9, 12),
            (10, 11),
            (11, 15),
            (12, 13),
            (13, 14),
            
            # Krug 3
            ('CABINET', 16),
            (16, 17),
            (16, 21),
            (17, 18),
            (18, 19),
            (18, 20),
            
            # Krug 4
            ('CABINET', 22),
            (22, 23),
            (22, 25),
            (23, 24),
            (25, 26),
            
            # Krug 5
            ('CABINET', 27),
            (27, 28),
            (27, 30),
            (28, 29),
            (29, 30),
        ]
        
        nodes_df = pd.DataFrame(nodes_data, columns=['id', 'circuit_label', 'x', 'y'])
        edges_df = pd.DataFrame(edges_data, columns=['from_node', 'to_node'])
        
        return nodes_df, edges_df
    
    def setup_gui(self):
        """Postavi GUI"""
        # Gornji okvir sa kontrolama
        top_frame = ttk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        ttk.Label(top_frame, text="Odaberi strujni krug:", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.circuit_var = tk.StringVar()
        self.circuit_combo = ttk.Combobox(top_frame, textvariable=self.circuit_var, 
                                          values=list(self.planer.circuits.keys()), 
                                          state="readonly", width=25)
        self.circuit_combo.pack(side=tk.LEFT, padx=5)
        self.circuit_combo.current(0)
        self.circuit_combo.bind('<<ComboboxSelected>>', self.on_circuit_change)
        
        ttk.Button(top_frame, text="Prikaži sve krugove", command=self.show_all_circuits).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Sažetak", command=self.show_summary).pack(side=tk.LEFT, padx=5)
        
        # Glavni okvir sa canvas-om
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Prikaži prvi krug
        self.show_circuit(list(self.planer.circuits.keys())[0])
    
    def show_circuit(self, circuit_label):
        """Prikaži jedan strujni krug"""
        # Očisti prethodni canvas
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        
        # Kreiraj novu figuru
        fig = Figure(figsize=(12, 8), dpi=100)
        ax = fig.add_subplot(111)
        
        self.planer.draw_circuit(ax, circuit_label)
        
        # Postavi canvas
        canvas = FigureCanvasTkAgg(fig, master=self.main_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def on_circuit_change(self, event=None):
        """Poziv kada se promijeni odabran strujni krug"""
        circuit = self.circuit_var.get()
        self.show_circuit(circuit)
    
    def show_all_circuits(self):
        """Prikaži sve strujne krugove"""
        # Očisti prethodni canvas
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        
        # Kreiraj figure za sve krugove
        num_circuits = len(self.planer.circuits)
        cols = 2
        rows = (num_circuits + 1) // 2
        
        fig = Figure(figsize=(16, 8*rows), dpi=100)
        
        for idx, circuit_label in enumerate(self.planer.circuits.keys(), 1):
            ax = fig.add_subplot(rows, cols, idx)
            self.planer.draw_circuit(ax, circuit_label)
        
        # Postavi canvas
        canvas = FigureCanvasTkAgg(fig, master=self.main_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def show_summary(self):
        """Prikaži sažetak u novom prozoru"""
        summary_window = tk.Toplevel(self.root)
        summary_window.title("Sažetak Rezultata")
        summary_window.geometry("900x700")
        
        # Kreiraj text widget
        text_widget = tk.Text(summary_window, font=("Courier New", 10), wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Umetni tekst
        summary_text = self.planer.get_summary_text()
        text_widget.insert(tk.END, summary_text)
        text_widget.config(state=tk.DISABLED)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(text_widget)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=text_widget.yview)

def main():
    root = tk.Tk()
    app = CablePlannerGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()