import os
import tqdm
import torch
import urllib
import argparse
from pathlib import Path
from data.provider import DataProvider
from reconstruction.utils.loading_utils import load_model, get_device
from reconstruction.image_reconstructor import ImageReconstructor
from reconstruction.options.inference_options import set_inference_options
from reconstruction.utils.voxelgrid import VoxelGrid
os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Image reconstruction')
    parser.add_argument('--h5file', help='Path to h5 file containing events for reconstruction.', default='')
    parser.add_argument('-c', '--path_to_model', type=str,
                        help='path to the model weights',
                        default='reconstruction/pretrained/E2VID_lightweight.pth.tar')
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--freq_hz', '-fhz', type=int, default=30, help='Frequency for reconstructing frames from events')
    parser.add_argument('--upsample_freq', '-ufhz', type=int, default=2, help='Frequency for upsampling the frequence of recontruction')
    parser.add_argument('--verbose', '-v',  action='store_true', default=False, help='Verbose output')

    set_inference_options(parser)

    args = parser.parse_args()

    # Data loader
    if not os.path.isfile(args.h5file):
        print('h5 file not provided')
        exit()
    h5_path = Path(args.h5file)
    freq_hz = args.freq_hz
    data_provider = DataProvider(h5_path, height=args.height, width=args.width, reconstruction_frequency_hz=args.freq_hz)

    # Load model to device
    print('Downloading E2VID checkpoint to {} ...'.format(args.path_to_model))
    if not os.path.isfile(args.path_to_model):
        e2vid_model = urllib.request.urlopen('http://rpg.ifi.uzh.ch/data/E2VID/models/E2VID_lightweight.pth.tar')
        with open(args.path_to_model, 'w+b') as f:
            f.write(e2vid_model.read())
        print('Done with downloading!')
    assert os.path.isfile(args.path_to_model)
    model = load_model(args.path_to_model)
    device = get_device(args.use_gpu)
    model = model.to(device)
    model.eval()

    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)
    else:
        assert os.path.isdir(args.output_folder)
    
    image_reconstructor = ImageReconstructor(model, args.height, args.width, model.num_bins, args)
    print('== Image reconstruction == ')
    print('Image size: {}x{}'.format(args.height, args.width))
    print('Will write images to: {}'.format(os.path.join(args.output_folder, args.dataset_name)))
    pbar = tqdm.tqdm(total=len(data_provider))
    for events in data_provider:
        if events.events.size > 0:
            grid_repr = VoxelGrid(model.num_bins, events.width, events.height, upsample_rate=args.upsample_freq)
            sliced_events = grid_repr.event_slicer(events.events, events.t_reconstruction)
            for i in range(len(sliced_events)):
                grid, ts = grid_repr.events_to_voxel_grid(sliced_events[i], events.t_reconstruction)
                event_tensor= torch.from_numpy(grid)
                if i==len(sliced_events)-1:
                    assert ts <= events.t_reconstruction
                    image_reconstructor.update_reconstruction(event_tensor, int(events.t_reconstruction)*1000, save=True, stamp=ts)
                    pbar.update(1)
                else:
                    image_reconstructor.update_reconstruction(event_tensor, int(ts)*1000, save=False, stamp=ts)