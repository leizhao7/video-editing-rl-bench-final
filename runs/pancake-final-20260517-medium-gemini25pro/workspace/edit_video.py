
from moviepy.editor import *

def create_pancake_tutorial():
    """
    Creates a vertical pancake tutorial video from the expert clip.
    """

    # Define the video clips with their start and end times (in seconds)
    clips_data = [
        {"start": 0, "end": 5, "caption": "1. Mix the batter until smooth."},
        {"start": 8, "end": 15, "caption": "2. Pour batter onto a hot pan."},
        {"start": 20, "end": 28, "caption": "3. Flip when bubbles appear."},
        {"start": 30, "end": 35, "caption": "4. Cook until golden brown."},
        {"start": 35, "end": 40, "caption": "5. Plate and enjoy your pancakes!"}
    ]

    # Load the expert clip
    video = VideoFileClip("work/pancake_expert.mp4")

    # Create a list to store the edited clips
    edited_clips = []

    for i, clip_data in enumerate(clips_data):
        # Trim the clip
        clip = video.subclip(clip_data["start"], clip_data["end"])

        # Crop and resize the clip to 9:16 aspect ratio
        (w, h) = clip.size
        # Crop a 9:16 rectangle from the center of the clip
        # The width will be h * 9 / 16
        crop_width = h * 9 / 16
        x1 = (w - crop_width) / 2
        x2 = w - x1
        cropped_clip = clip.crop(x1=x1, y1=0, x2=x2, y2=h)
        resized_clip = cropped_clip.resize(height=1280)

        # Add a caption to the clip
        txt_clip = TextClip(
            clip_data["caption"],
            fontsize=70,
            color='white',
            font='Arial',
            stroke_color='black',
            stroke_width=2
        )
        txt_clip = txt_clip.set_pos('center').set_duration(clip.duration)

        # Composite the video and text clips
        video_with_caption = CompositeVideoClip([resized_clip, txt_clip])

        # Add the edited clip to the list
        edited_clips.append(video_with_caption)

    # Concatenate the clips
    final_clip = concatenate_videoclips(edited_clips)

    # Normalize the audio
    final_clip = final_clip.audio_normalize()

    # Write the final video to a file
    final_clip.write_videofile(
        "submit/output.mp4",
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True
    )

if __name__ == "__main__":
    create_pancake_tutorial()
