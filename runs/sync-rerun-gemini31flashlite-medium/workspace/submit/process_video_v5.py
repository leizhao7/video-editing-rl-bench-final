import subprocess

filter_complex = (
    "[0:v]trim=start=3:end=48[v1];"
    "[0:v]trim=start=52:end=95[v2];"
    "[v1][v2]concat=n=2:v=1[outv];"
    "[0:a]atrim=start=3:end=48[a1];"
    "[0:a]atrim=start=52:end=95[a2];"
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
