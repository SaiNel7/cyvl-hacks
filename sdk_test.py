import cyvl
import numpy as np
scene = cyvl.load_scene("somerville")
frame = scene.nearest_frame(-71.1218, 42.3967)

# Pose confirmed working — extract bearing for wall orientation
pose = frame.pose
# Forward vector is third column of rotation matrix
forward = pose[:3, 2]
bearing_deg = np.degrees(np.arctan2(forward[0], forward[1])) % 360
print("camera bearing:", bearing_deg)

# Introspect Projected object
pts = frame.points_in_view()
print(type(pts))
print(dir(pts))

# Try likely attributes
for attr in ['xyz', 'points', 'coords', 'data', 'array', 'positions', 'df']:
    if hasattr(pts, attr):
        val = getattr(pts, attr)
        print(f"pts.{attr}:", type(val), getattr(val, 'shape', ''))

# Try measure — use a different frame if this one has no own-pass lidar
# Find a frame that has its own pass
frames_layer = scene.imagery
print(frames_layer.columns.tolist())
print(frames_layer[frames_layer['has_lidar_pass'] == True].head(3) if 'has_lidar_pass' in frames_layer.columns else "no has_lidar_pass column")

# Try measure anyway
try:
    m = cyvl.measure(frame, (1500, 1500), (2400, 1500))
    print("measure:", m)
except Exception as e:
    print("measure error:", e)

# Full layer dump
for layer in ['assets', 'distresses', 'pavements', 'signs', 'markings', 'inspection_cells', 'rollup']:
    df = getattr(scene, layer)
    print(f"\n--- {layer} ({df.shape}) ---")
    print(df.columns.tolist())
    print(df.head(1).to_dict('records'))