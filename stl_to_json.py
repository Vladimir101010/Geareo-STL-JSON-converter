import json
import os
import struct
import math
import sys
import zlib
import tkinter as tk
from tkinter import filedialog, messagebox

def create_base_project():
    return {
        "version": "Vlad was here",
        "parts": {
            "lastId": 0,
            "entities": []
        },
        "camera": {
            "px": 0.0, "py": 2.0, "pz": 0,
            "rx": 10, "ry": 30, "rz": 0, "zoom": 1
        },
        "settings": {
            "data": {
                "advanced": True, "scene": "", "collisionDetectionMode": 2,
                "physicsSteps": 6, "dynamicPhysicsStep": False, "limitless": False,
                "handleGrid": 0.125, "moveGrid": 0.125, "rotateGrid": 15.0
            }
        },
        "hub": {
            "lastId": 2,
            "channels": [
                {"id": 1, "name": "global", "color": "#FFE1B6", "keyboard": True, "global": False, "isLocked": False}
            ],
            "circuits": []
        },
        "selector": {"items": []}
    }

def write_png(filename, width, height, rgb_buffer):
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)
        for x in range(width):
            r, g, b = rgb_buffer[y * width + x]
            raw_data.extend((r, g, b))
    compressed = zlib.compress(bytes(raw_data), 9)
    
    def make_chunk(chunk_type, data):
        return struct.pack('>I', len(data)) + chunk_type + data + struct.pack('>I', zlib.crc32(chunk_type + data) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    png_bytes = b'\x89PNG\r\n\x1a\n' + make_chunk(b'IHDR', ihdr) + make_chunk(b'IDAT', compressed) + make_chunk(b'IEND', b'')
    with open(filename, 'wb') as f:
        f.write(png_bytes)

def load_stl(filepath):
    triangles = []
    default_color = (255, 255, 255)
    
    with open(filepath, 'rb') as f:
        header = f.read(80)
        if header[0:5].lower() == b'solid':
            f.seek(0)
            content = f.read(1024).decode('ascii', errors='ignore')
            if 'facet' in content:
                return load_stl_ascii(filepath)
                
        f.seek(80)
        count_bytes = f.read(4)
        if not count_bytes:
            return triangles
        count = struct.unpack('<I', count_bytes)[0]
        
        for _ in range(count):
            data = f.read(50)
            if len(data) < 50:
                break
            unpacked = struct.unpack('<12fH', data)
            v1 = unpacked[3:6]
            v2 = unpacked[6:9]
            v3 = unpacked[9:12]
            attr = unpacked[12]
            
            color = default_color
            if attr & 0x8000:
                r = int(((attr >> 10) & 0x1F) * (255 / 31))
                g = int(((attr >> 5) & 0x1F) * (255 / 31))
                b = int((attr & 0x1F) * (255 / 31))
                color = (r, g, b)
                
            triangles.append((v1, v2, v3, color))
            
    return triangles

def load_stl_ascii(filepath):
    triangles = []
    current_tri = []
    default_color = (255, 255, 255)
    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts: 
                continue
            if parts[0] == 'vertex':
                current_tri.append((float(parts[1]), float(parts[2]), float(parts[3])))
                if len(current_tri) == 3:
                    triangles.append((current_tri[0], current_tri[1], current_tri[2], default_color))
                    current_tri = []
    return triangles

def render_thumbnail(triangles, filename="thumbnail.png", width=256, height=256):
    if not triangles:
        write_png(filename, width, height, [(30, 30, 30)] * (width * height))
        return

    ax, ay = math.radians(25), math.radians(-45)
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    
    rot_tris = []
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    for v1, v2, v3, col in triangles:
        rvs = []
        for v in (v1, v2, v3):
            x1 = v[0]*cy + v[2]*sy
            y1 = v[1]
            z1 = -v[0]*sy + v[2]*cy
            x2 = x1
            y2 = y1*cx - z1*sx
            z2 = y1*sx + z1*cx
            rvs.append((x2, y2, z2))
            min_x = min(min_x, x2); max_x = max(max_x, x2)
            min_y = min(min_y, y2); max_y = max(max_y, y2)
            min_z = min(min_z, z2); max_z = max(max_z, z2)
        
        e1 = (rvs[1][0]-rvs[0][0], rvs[1][1]-rvs[0][1], rvs[1][2]-rvs[0][2])
        e2 = (rvs[2][0]-rvs[0][0], rvs[2][1]-rvs[0][1], rvs[2][2]-rvs[0][2])
        nx = e1[1]*e2[2] - e1[2]*e2[1]
        ny = e1[2]*e2[0] - e1[0]*e2[2]
        nz = e1[0]*e2[1] - e1[1]*e2[0]
        nl = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
        rot_tris.append((rvs[0], rvs[1], rvs[2], (nx/nl, ny/nl, nz/nl), col))

    dx = max_x - min_x or 1.0
    dy = max_y - min_y or 1.0
    scale = min((width - 40) / dx, (height - 40) / dy)
    mid_x = (min_x + max_x) / 2.0
    mid_y = (min_y + max_y) / 2.0
    
    z_buf = [float('-inf')] * (width * height)
    rgb_buf = [(28, 30, 34)] * (width * height)
    lx, ly, lz = 0.408, 0.408, 0.816
    
    for v1, v2, v3, norm, base_col in rot_tris:
        dot = norm[0]*lx + norm[1]*ly + norm[2]*lz
        intensity = max(0.3, min(1.0, abs(dot)))
        r = int(base_col[0] * intensity)
        g = int(base_col[1] * intensity)
        b = int(base_col[2] * intensity)
        
        sx1 = (v1[0] - mid_x) * scale + width / 2.0
        sy1 = height / 2.0 - (v1[1] - mid_y) * scale
        sx2 = (v2[0] - mid_x) * scale + width / 2.0
        sy2 = height / 2.0 - (v2[1] - mid_y) * scale
        sx3 = (v3[0] - mid_x) * scale + width / 2.0
        sy3 = height / 2.0 - (v3[1] - mid_y) * scale
        
        min_px = max(0, int(min(sx1, sx2, sx3)))
        max_px = min(width - 1, int(max(sx1, sx2, sx3)))
        min_py = max(0, int(min(sy1, sy2, sy3)))
        max_py = min(height - 1, int(max(sy1, sy2, sy3)))
        
        denom = (sy2 - sy3)*(sx1 - sx3) + (sx3 - sx2)*(sy1 - sy3)
        if abs(denom) < 1e-6:
            continue
        
        for py in range(min_py, max_py + 1):
            for px in range(min_px, max_px + 1):
                w1 = ((sy2 - sy3)*(px - sx3) + (sx3 - sx2)*(py - sy3)) / denom
                w2 = ((sy3 - sy1)*(px - sx3) + (sx1 - sx3)*(py - sy3)) / denom
                w3 = 1.0 - w1 - w2
                if w1 >= 0 and w2 >= 0 and w3 >= 0:
                    z = w1 * v1[2] + w2 * v2[2] + w3 * v3[2]
                    idx = py * width + px
                    if z > z_buf[idx]:
                        z_buf[idx] = z
                        rgb_buf[idx] = (r, g, b)
    
    write_png(filename, width, height, rgb_buf)

def voxelize_and_build(triangles, target_max_voxels=1200):
    if not triangles:
        return {}, 0.5
        
    min_p = [float('inf')]*3
    max_p = [float('-inf')]*3
    for tri in triangles:
        for v in tri[:3]:
            for i in range(3):
                min_p[i] = min(min_p[i], v[i])
                max_p[i] = max(max_p[i], v[i])

    center = [(min_p[i] + max_p[i])/2.0 for i in range(3)]
    size = [max_p[i] - min_p[i] for i in range(3)]
    max_dim = max(size) or 1.0

    pitch = max_dim / 16.0
    voxels = {}

    for pitch_factor in [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]:
        curr_pitch = pitch * pitch_factor
        voxels.clear()
        
        for v1, v2, v3, color in triangles:
            hex_color = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
            
            p1 = ((v1[0]-center[0]), (v1[1]-center[1]), (v1[2]-min_p[2]))
            p2 = ((v2[0]-center[0]), (v2[1]-center[1]), (v2[2]-min_p[2]))
            p3 = ((v3[0]-center[0]), (v3[1]-center[1]), (v3[2]-min_p[2]))

            e1 = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2 + (p2[2]-p1[2])**2)
            e2 = math.sqrt((p3[0]-p2[0])**2 + (p3[1]-p2[1])**2 + (p3[2]-p2[2])**2)
            e3 = math.sqrt((p1[0]-p3[0])**2 + (p1[1]-p3[1])**2 + (p1[2]-p3[2])**2)
            max_e = max(e1, e2, e3)

            steps = int(max_e / (curr_pitch * 0.5)) + 1
            for i in range(steps + 1):
                u = i / steps if steps > 0 else 0.0
                for j in range(steps - i + 1):
                    v = j / steps if steps > 0 else 0.0
                    w = 1.0 - u - v
                    px = u*p1[0] + v*p2[0] + w*p3[0]
                    py = u*p1[1] + v*p2[1] + w*p3[1]
                    pz = u*p1[2] + v*p2[2] + w*p3[2]
                    
                    vx = round(px / curr_pitch) * curr_pitch
                    vy = round(py / curr_pitch) * curr_pitch
                    vz = round(pz / curr_pitch) * curr_pitch
                    
                    key = (vx, vy, vz)
                    if key not in voxels:
                        voxels[key] = hex_color

        if len(voxels) <= target_max_voxels:
            break

    return voxels, curr_pitch

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("STL to Data Converter")
        self.root.geometry("380x470")
        self.root.resizable(False, False)
        self.root.configure(bg="#1E1E24")

        self.label_title = tk.Label(root, text="STL Converter", font=("Arial", 16, "bold"), fg="#FFFFFF", bg="#1E1E24")
        self.label_title.pack(pady=10)

        self.btn_browse = tk.Button(root, text="Select STL File", command=self.process_file, font=("Arial", 11, "bold"), bg="#4A90E2", fg="#FFFFFF", activebackground="#357ABD", activeforeground="#FFFFFF", padx=15, pady=6, bd=0)
        self.btn_browse.pack(pady=5)

        self.frame_scale = tk.Frame(root, bg="#1E1E24")
        self.frame_scale.pack(pady=5)

        self.label_scale = tk.Label(self.frame_scale, text="Cube Scale Factor:", font=("Arial", 10), fg="#FFFFFF", bg="#1E1E24")
        self.label_scale.pack(side=tk.LEFT, padx=5)

        self.scale_var = tk.DoubleVar(value=1.0)
        self.spin_scale = tk.Spinbox(self.frame_scale, from_=0.1, to=10.0, increment=0.1, textvariable=self.scale_var, width=6, font=("Arial", 10))
        self.spin_scale.pack(side=tk.LEFT, padx=5)

        self.canvas_img = tk.Canvas(root, width=200, height=200, bg="#1C1D21", highlightthickness=1, highlightbackground="#333333")
        self.canvas_img.pack(pady=10)
        
        self.label_status = tk.Label(root, text="Select an STL to convert", font=("Arial", 10), fg="#A0A0A0", bg="#1E1E24")
        self.label_status.pack(pady=5)
        
        self.img_ref = None

    def process_file(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = filedialog.askopenfilename(
            initialdir=script_dir,
            title="Select STL File",
            filetypes=[("STL Files", "*.stl")]
        )
        if not file_path:
            return

        try:
            self.label_status.config(text="Parsing STL...", fg="#FFCC00")
            self.root.update_idletasks()

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            parent_dir = os.path.dirname(file_path) or script_dir
            out_folder = os.path.join(parent_dir, base_name)
            os.makedirs(out_folder, exist_ok=True)

            thumb_path = os.path.join(out_folder, "thumbnail.png")
            data_path = os.path.join(out_folder, "data.json")
            manifest_path = os.path.join(out_folder, "manifest.json")

            triangles = load_stl(file_path)
            if not triangles:
                messagebox.showerror("Error", "Failed to parse STL or file is empty.")
                return

            render_thumbnail(triangles, thumb_path, 200, 200)

            voxels, block_size = voxelize_and_build(triangles, target_max_voxels=1200)

            scale_factor = max(0.01, float(self.scale_var.get()))
            scaled_block_size = round(block_size * scale_factor, 4)

            project = create_base_project()
            parts = project["parts"]
            
            for idx, ((vx, vy, vz), color) in enumerate(voxels.items(), start=1):
                parts["lastId"] = idx
                parts["entities"].append({
                    "key": "box",
                    "id": idx,
                    "data": {
                        "width": scaled_block_size,
                        "height": scaled_block_size,
                        "depth": scaled_block_size,
                        "color": color,
                        "material": "wod",
                        "name": f"b{idx}",
                        "_c": [round(vx * scale_factor, 4), round((vz * scale_factor) + 2.0, 4), round(vy * scale_factor, 4), 0.0, 0.0, 0.0],
                        "_m": {},
                        "isStatic": True
                    }
                })

            with open(data_path, "w") as f:
                json.dump(project, f, separators=(',', ':'))

            manifest_data = {
                "type": "project",
                "version": "0.8.2-demo+156-26.235",
                "data": "data.json",
                "thumbnail": "thumbnail.png"
            }
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f, separators=(',', ':'))

            size_kb = os.path.getsize(data_path) / 1024.0

            if os.path.exists(thumb_path):
                self.img_ref = tk.PhotoImage(file=thumb_path)
                self.canvas_img.create_image(100, 100, image=self.img_ref)

            self.label_status.config(text=f"Created folder '{base_name}' ({size_kb:.1f} KB)", fg="#00FF66")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.label_status.config(text="Error processing file", fg="#FF4D4D")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()