import ast
import subprocess

with open('submit/segments.txt', 'r') as f:
    segments = ast.literal_eval(f.read())

# Filter for meaningful segments (duration > 0.1s)
meaningful_segments = [seg for seg in segments if (seg[1] - seg[0]) > 0.1]

filter_complex = ""
for i, (start, end) in enumerate(meaningful_segments):
    filter_complex += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
    filter_complex += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"

concat_str = "".join([f"[v{i}][a{i}]" for i in range(len(meaningful_segments))])
filter_complex += f"{concat_str}concat=n={len(meaningful_segments)}:v=1:a=1[outv][outa]"

cmd = [
    'ffmpeg', '-i', 'materials/source.mp4',
    '-filter_complex', filter_complex,
    '-map', '[outv]', '-map', '[outa]',
    '-c:v', 'libx264', '-c:a', 'aac', '-ar', '48000', '-b:a', '128k',
    '-s', '1280x720', '-r', '30', 'submit/output.mp4', '-y'
]

subprocess.run(cmd)
