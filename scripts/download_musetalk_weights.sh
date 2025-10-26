#!/bin/bash

# Set root directory
MODEL_DIR="models"

# Create all necessary subdirectories
mkdir -p "$MODEL_DIR"
# mkdir -p "$MODEL_DIR"
mkdir -p "$MODEL_DIR/musetalkV15"
# mkdir -p "$MODEL_DIR/syncnet"
# mkdir -p "$MODEL_DIR/dwpose"
mkdir -p "$MODEL_DIR/whisper"
mkdir -p "$MODEL_DIR/sd-vae-ft-mse"
mkdir -p "$MODEL_DIR/face-parse-bisent"


# Install required packages
pip install -U "huggingface_hub[cli]"

# Set HuggingFace mirror (for use in mainland China)
export HF_ENDPOINT=https://hf-mirror.com

# Download MuseTalk weights (TMElyralab/MuseTalk) - download to root directory, may contain subdirectories
echo "Downloading MuseTalk main weights to $MODEL_DIR..."
huggingface-cli download TMElyralab/MuseTalk --local-dir "$MODEL_DIR" --local-dir-use-symlinks False


echo "Downloading SD VAE weights to $MODEL_DIR/sd-vae-ft-mse..."
huggingface-cli download stabilityai/sd-vae-ft-mse --local-dir "$MODEL_DIR/sd-vae-ft-mse" --local-dir-use-symlinks False


# echo "Downloading Whisper weights to $MODEL_DIR/whisper..."
# huggingface-cli download openai/whisper-tiny --local-dir "$MODEL_DIR/whisper" --local-dir-use-symlinks False --include "config.json" "pytorch_model.bin" "preprocessor_config.json"

# echo "Downloading DWPose weights to $MODEL_DIR/dwpose..."
# huggingface-cli download yzd-v/DWPose --local-dir "$MODEL_DIR/dwpose" --local-dir-use-symlinks False --include "dw-ll_ucoco_384.pth"

# # Download SyncNet weights to syncnet subdirectory
# echo "Downloading SyncNet weights to $MODEL_DIR/syncnet..."
# huggingface-cli download ByteDance/LatentSync --local-dir "$MODEL_DIR/syncnet" --local-dir-use-symlinks False --include "latentsync_syncnet.pt"


echo "Downloading Face Parse Bisent weights to $MODEL_DIR/face-parse-bisent..."
huggingface-cli download ManyOtherFunctions/face-parse-bisent --local-dir "$MODEL_DIR/face-parse-bisent" --local-dir-use-symlinks False --include "79999_iter.pth" "resnet18-5c106cde.pth"

# echo "Downloading s3fd-619a316812 weights to $MODEL_DIR/s3fd-619a316812..."
# git clone https://www.modelscope.cn/HaveAnApplePie/s3fd-619a316812.git $MODEL_DIR/s3fd-619a316812

echo "All download commands have been executed, but the model files may not be downloaded. Please check the following directories and files exist:"
echo "\n- models/musetalk/ (MuseTalk main weights)"
echo "- models/musetalk/whisper/config.json"
echo "- models/musetalk/whisper/pytorch_model.bin"
echo "- models/musetalk/whisper/preprocessor_config.json"
# echo "- models/musetalk/dwpose/dw-ll_ucoco_384.pth"
# echo "- models/musetalk/syncnet/latentsync_syncnet.pt"
echo "- models/sd-vae-ft-mse/ (SD VAE weights)"
echo "- models/face-parse-bisent/79999_iter.pth"
echo "- models/face-parse-bisent/resnet18-5c106cde.pth"
echo "\nIf any file is missing, please check the download logs above."

echo "If files are missing, run the script again."

