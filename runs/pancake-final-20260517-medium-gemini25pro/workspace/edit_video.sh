
#!/bin/bash

# Clean up previous attempts
rm -f work/part*.mp4

# Create the video segments
ffmpeg -y -i work/pancake_expert.mp4 -ss 0 -to 5 -vf "crop=ih*9/16:ih,scale=720:1280,drawtext=text='1. Mix the batter until smooth.':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=50:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5" -c:a copy work/part1.mp4
ffmpeg -y -i work/pancake_expert.mp4 -ss 8 -to 15 -vf "crop=ih*9/16:ih,scale=720:1280,drawtext=text='2. Pour batter onto a hot pan.':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=50:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5" -c:a copy work/part2.mp4
ffmpeg -y -i work/pancake_expert.mp4 -ss 20 -to 28 -vf "crop=ih*9/16:ih,scale=720:1280,drawtext=text='3. Flip when bubbles appear.':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=50:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5" -c:a copy work/part3.mp4
ffmpeg -y -i work/pancake_expert.mp4 -ss 30 -to 35 -vf "crop=ih*9/16:ih,scale=720:1280,drawtext=text='4. Cook until golden brown.':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=50:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5" -c:a copy work/part4.mp4
ffmpeg -y -i work/pancake_expert.mp4 -ss 35 -to 40 -vf "crop=ih*9/16:ih,scale=720:1280,drawtext=text='5. Plate and enjoy your pancakes!':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=50:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5" -c:a copy work/part5.mp4

# Create a file with the list of clips to concatenate
echo "file 'part1.mp4'" > work/concat_list.txt
echo "file 'part2.mp4'" >> work/concat_list.txt
echo "file 'part3.mp4'" >> work/concat_list.txt
echo "file 'part4.mp4'" >> work/concat_list.txt
echo "file 'part5.mp4'" >> work/concat_list.txt

# Concatenate the clips
ffmpeg -y -f concat -safe 0 -i work/concat_list.txt -c copy work/final_video_no_audio.mp4

# Extract and normalize the audio in one step
ffmpeg -y -i work/final_video_no_audio.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=summary" work/audio_normalized.aac

# Combine the video with the normalized audio
ffmpeg -y -i work/final_video_no_audio.mp4 -i work/audio_normalized.aac -c:v copy -c:a aac -shortest submit/output.mp4
