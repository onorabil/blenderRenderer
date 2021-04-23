import shutil
import glob
import json
from os import getcwd
from os.path import join
from pathlib import Path

DATASET = 'bdataset_stereo'
wd = Path(getcwd())
root = wd.parent
data_path = Path(join(wd, 'out'))

Path(join(root, DATASET)).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET)).mkdir(parents=True, exist_ok=True)

left_images = sorted(glob.glob(str(data_path / '*stereo_L.png'), recursive=True))
right_images = sorted(glob.glob(str(data_path / '*stereo_R.png'), recursive=True))
left_depths = sorted(glob.glob(str(data_path / '*depth_L.exr'), recursive=True))
right_depths = sorted(glob.glob(str(data_path / '*depth_R.exr'), recursive=True))

STEP = 3

JSON_TRAIN_DATA = []
JSON_TEST_DATA = []

index = 0
for i, (left_img, right_img, left_depth, right_depth) in enumerate(zip(left_images, right_images, left_depths, right_depths)):
    shutil.copy(left_img, join(root, DATASET))
    shutil.copy(right_img, join(root, DATASET))
    shutil.copy(left_depth, join(root, DATASET))
    shutil.copy(right_depth, join(root, DATASET))
    (JSON_TEST_DATA if i % STEP == 0 else JSON_TRAIN_DATA).append({
        "imageL": Path(left_img).name,
        "imageR": Path(right_img).name,
        "depthL": Path(left_depth).name,
        "depthR": Path(right_depth).name
    })

with open(join(root, DATASET, "train.json"), "w") as f:
    json.dump(JSON_TRAIN_DATA, f)
with open(join(root, DATASET, "test.json"), "w") as f:
    json.dump(JSON_TEST_DATA, f)