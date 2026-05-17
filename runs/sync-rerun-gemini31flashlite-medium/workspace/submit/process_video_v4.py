import subprocess

# Only remove:
# Start: 0.0 - 2.5s (2.5s removed)
# Middle: 48.7 - 51.2s (2.5s removed)
# End: 100.3 - 101.7s (1.4s removed)
# Total removed: ~6.4s. 
# Original: 101.7s. New: ~95s. This should fit!

filter_complex = (
    "[0:v]trim=start=2.5:end=48.7[v1];"
    "[0:v]trim=start=51.2:end=100.3[v2];"
    "[v1][v2]concat=n=2:v=1[outv];"
    "[0:a]atrim=start=2.5:end=48.7[a1];"
    "[0:a]atrim=start=51.2:end=100.3[a2];"
    "[a1][a2]concat=n=2:v=0:a=1[outa]"
)

cmd = [
    'ffmpeg', '-i', 'materials/source.mp4',
    '-filter_complex', filter_complex,
    '-map', '[outv]', '-map', '[outa]',
    '-c:v', 'libx264', '-c:a', 'aac', '-ar', '48000', '-b:a', '128k',
    '-s', '1280x720', '-r', '30', 'submit/output.mp4', '-y'
]

subprocess.run(cmd)
