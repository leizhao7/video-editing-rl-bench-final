import subprocess

# Trim the first 5s.
filter_complex = (
    "[0:v]trim=start=5,setpts=PTS-STARTPTS[outv];"
    "[0:a]atrim=start=5,asetpts=PTS-STARTPTS[outa]"
)

cmd = [
    'ffmpeg', '-i', 'materials/source.mp4',
    '-filter_complex', filter_complex,
    '-map', '[outv]', '-map', '[outa]',
    '-c:v', 'libx264', '-c:a', 'aac', '-ar', '48000', '-b:a', '128k',
    '-s', '1280x720', '-r', '30', 'submit/output.mp4', '-y'
]

subprocess.run(cmd)
