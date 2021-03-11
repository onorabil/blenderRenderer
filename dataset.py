import shutil
import glob
from os import getcwd
from os.path import join
from pathlib import Path

DATASET='bdataset'
wd = Path(getcwd())
root = wd.parent
data_path = Path(join(wd, 'out'))

Path(join(root, DATASET, 'images', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'images', 'test')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'labels', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'labels', 'test')).mkdir(parents=True, exist_ok=True)

images = glob.glob(str(data_path / '*.png'), recursive=True)
labels = glob.glob(str(data_path / '*.txt'), recursive=True)

STEP = 3

index = 0
for i, image in enumerate(images):
    shutil.copy(image, join(root, DATASET, 'images', 'test' if (i // 4) % STEP == 0 else 'train'))
    
for i, label in enumerate(labels):
    shutil.copy(label, join(root, DATASET, 'labels', 'test' if i % STEP == 0 else 'train'))
