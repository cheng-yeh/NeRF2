#!/bin/bash
#SBATCH -J nerf2_test                           # Job name
#SBATCH --account=gts-rs275                     # charge account
#SBATCH -N 1 --gres=gpu:RTX_6000:1              # Number of nodes and cores per node required
#SBATCH --mem-per-gpu=10G                       # Memory per core
#SBATCH -t 144                                  # Duration of the job (Ex: 15 mins)
#SBATCH -q inferno                              # QOS Name
#SBATCH -o Report-%j.out                        # Combined output and error messages file
#SBATCH --mail-type=BEGIN,END,FAIL              # Mail preferences
#SBATCH --mail-user=cchen847@gatech.edu         # E-mail address for notifications
cd $SLURM_SUBMIT_DIR                            # Change to working directory

module load anaconda3                           # Load module dependencies
pip install configargparse==1.4
pip install matplotlib==3.7.1 
pip install numpy==1.24.3
pip install pandas==1.5.3
pip install pillow==9.4.0
pip install pytorch==2.0.1
pip install scikit-learn==1.3.0
pip install scipy==1.10.1
pip install tensorboardx==2.2
pip install torchvision==0.15.2
pip install tqdm
pip install yaml
pip install einops
pip install imageio
pip install scikit-image
python nerf2_runner.py --mode train --config configs/mimo-csi.yml --dataset_type mimo --gpu 0
python nerf2_runner.py --mode test --config configs/mimo-csi.yml --dataset_type mimo --gpu 0
