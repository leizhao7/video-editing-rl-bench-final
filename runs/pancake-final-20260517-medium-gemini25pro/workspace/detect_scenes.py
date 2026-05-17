
import scenedetect
import os

def find_scenes(video_path, output_dir):
    # Create a SceneManager and add a ContentDetector.
    scene_manager = scenedetect.SceneManager()
    scene_manager.add_detector(scenedetect.ContentDetector())

    # Create a directory to store the scene images
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Use a backend to process the video.
    video = scenedetect.open_video(video_path)
    scene_manager.detect_scenes(video=video, show_progress=True)

    # Get the list of scenes.
    scene_list = scene_manager.get_scene_list()

    # Print out the scene list.
    print(f"Detected {len(scene_list)} scenes.")
    for i, scene in enumerate(scene_list):
        print(f"Scene {i+1}: {scene[0].get_timecode()} - {scene[1].get_timecode()}")

    # Save a frame from each scene
    scenedetect.save_images(
        scene_list,
        video,
        num_images=1,
        output_dir=output_dir,
        image_name_template='$SCENE_NUMBER'
    )

if __name__ == "__main__":
    video_path = "materials/source.mp4"
    output_dir = "work/scenes"
    find_scenes(video_path, output_dir)
