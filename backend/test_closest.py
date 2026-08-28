import csv
import math

video_id = "L22_V030"
target_frame_idx = 1200

map_file = f"data/map_keyframes/{video_id}.csv"
closest_n = None
min_diff = math.inf
with open(map_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        idx = int(row['frame_idx'])
        diff = abs(idx - target_frame_idx)
        if diff < min_diff:
            min_diff = diff
            closest_n = int(row['n'])

print(f"Target: {target_frame_idx}, Closest frame_idx diff: {min_diff}, closest n: {closest_n:03d}.jpg")
