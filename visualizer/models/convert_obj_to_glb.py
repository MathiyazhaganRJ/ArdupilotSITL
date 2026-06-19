"""
Convert Endurance.obj to Endurance.glb using pygltflib.
Reads OBJ vertices + faces and packs into a valid GLB binary.
"""
import struct, json, math
import numpy as np
from pygltflib import GLTF2, Scene, Node, Mesh, Primitive, Buffer, BufferView, Accessor
from pygltflib import FLOAT, UNSIGNED_INT, ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER
import pygltflib

OBJ_FILE = "Endurance.obj"
GLB_FILE = "Endurance.glb"

print(f"Reading {OBJ_FILE}...")

vertices = []
faces = []

with open(OBJ_FILE, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("v "):
            parts = line.split()
            # OpenVSP uses Z-up, swap to Y-up for glTF: (x, z, -y)
            x = float(parts[1])
            y = float(parts[2])
            z = float(parts[3])
            vertices.append([x, z, -y])
        elif line.startswith("f "):
            parts = line.split()[1:]
            indices = []
            for p in parts:
                # Handle f v, f v/vt, f v/vt/vn, f v//vn
                idx = int(p.split("/")[0]) - 1  # OBJ is 1-indexed
                indices.append(idx)
            # Triangulate if needed (fan triangulation)
            for i in range(1, len(indices) - 1):
                faces.append([indices[0], indices[i], indices[i + 1]])

print(f"  Vertices: {len(vertices)}")
print(f"  Triangles: {len(faces)}")

# Convert to numpy arrays
verts_np = np.array(vertices, dtype=np.float32)
faces_np = np.array(faces, dtype=np.uint32)

# Recenter to origin
centroid = (verts_np.max(axis=0) + verts_np.min(axis=0)) / 2.0
verts_np -= centroid

# Print final bounding box
bmin = verts_np.min(axis=0)
bmax = verts_np.max(axis=0)
print(f"  Bounding box after centering:")
print(f"    X: {bmin[0]:.3f} to {bmax[0]:.3f}  ({bmax[0]-bmin[0]:.3f} m)")
print(f"    Y: {bmin[1]:.3f} to {bmax[1]:.3f}  ({bmax[1]-bmin[1]:.3f} m)")
print(f"    Z: {bmin[2]:.3f} to {bmax[2]:.3f}  ({bmax[2]-bmin[2]:.3f} m)")

# Pack binary buffers
verts_bytes = verts_np.tobytes()
faces_bytes = faces_np.tobytes()
total_bytes = len(verts_bytes) + len(faces_bytes)

gltf = GLTF2()
gltf.scene = 0
gltf.scenes = [Scene(nodes=[0])]
gltf.nodes = [Node(mesh=0)]

gltf.meshes = [Mesh(primitives=[Primitive(
    attributes={"POSITION": 1},
    indices=0,
    material=0
)])]

gltf.materials = [pygltflib.Material(
    name="EnduranceMaterial",
    pbrMetallicRoughness=pygltflib.PbrMetallicRoughness(
        baseColorFactor=[0.2, 0.5, 0.9, 1.0],   # Blue-grey body
        metallicFactor=0.3,
        roughnessFactor=0.6,
    ),
    doubleSided=True
)]

gltf.buffers = [Buffer(byteLength=total_bytes)]

gltf.bufferViews = [
    # indices
    BufferView(buffer=0, byteOffset=0, byteLength=len(faces_bytes), target=ELEMENT_ARRAY_BUFFER),
    # vertices
    BufferView(buffer=0, byteOffset=len(faces_bytes), byteLength=len(verts_bytes), target=ARRAY_BUFFER),
]

gltf.accessors = [
    # indices accessor
    Accessor(bufferView=0, componentType=UNSIGNED_INT, count=len(faces_np)*3, type="SCALAR"),
    # positions accessor
    Accessor(
        bufferView=1, componentType=FLOAT, count=len(verts_np), type="VEC3",
        min=bmin.tolist(), max=bmax.tolist()
    ),
]

gltf.set_binary_blob(faces_bytes + verts_bytes)

gltf.save_binary(GLB_FILE)
print(f"\n✅ Saved: {GLB_FILE}")
import os
size_kb = os.path.getsize(GLB_FILE) / 1024
print(f"   File size: {size_kb:.1f} KB")
