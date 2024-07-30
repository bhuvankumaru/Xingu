import os
import glob
import logging
import subprocess
from datetime import datetime
import argparse

def extract_date_from_filename(filename):
    date_str = os.path.basename(filename).split('_')[2][0:8]
    try:
        return datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        logging.error(f"Failed to parse date from filename: {filename}")
        return None

def find_nearest_date_file(directory_path, target_date):
    nearest_date_diff = None
    nearest_date_file = None

    for filename in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, filename)) and filename.lower().endswith('.tif'):
            extracted_date = extract_date_from_filename(filename)
            if extracted_date:
                date_diff = abs(extracted_date - target_date)
                if nearest_date_diff is None or date_diff < nearest_date_diff:
                    nearest_date_diff = date_diff
                    nearest_date_file = os.path.join(directory_path, filename)
    return nearest_date_file

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def main(slc1_dir, slc2_dir, merged_file_dir, bbox):
    # Initialize logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Ensure output directories exist
    ensure_directory_exists(merged_file_dir)

    subset_file_dir = os.path.join(merged_file_dir, 'subset_tifs')
    ensure_directory_exists(subset_file_dir)

    # Merge SLCs from different tracks
    slc_list = glob.glob(os.path.join(slc1_dir, '*_VH.tif'))

    for slc in slc_list:
        slc1_date = extract_date_from_filename(slc)
        if slc1_date:
            slc_file_2 = find_nearest_date_file(slc2_dir, slc1_date)
            if slc_file_2:
                slc2_date = extract_date_from_filename(slc_file_2)
                if slc2_date:
                    out_name = os.path.join(merged_file_dir, f'{slc1_date.strftime("%Y%m%d")}_604_599_merged_VH.tif')
                    command = f"gdal_merge.py -o {out_name} -a_nodata -9999 {slc} {slc_file_2}"
                    logging.info(f"Merging files: {slc} and {slc_file_2} into {out_name}")
                    subprocess.run(command.split())
                else:
                    logging.warning(f"Failed to extract date from second file: {slc_file_2}")
            else:
                logging.warning(f"No matching file found in target path for date: {slc1_date}")
        else:
            logging.warning(f"Failed to extract date from file: {slc}")

    # Subset merged SLCs
    merged_slc_list = glob.glob(os.path.join(merged_file_dir, '*_VH.tif'))

    for slc in merged_slc_list:
        output_path = os.path.join(subset_file_dir, 'subset_' + os.path.basename(slc))
        command = 'gdalwarp -te {} {} {} {} {} {}'.format(bbox[0], bbox[1], bbox[2], bbox[3], slc, output_path)
        logging.info(f"Subsetting file: {slc} to {output_path}")
        subprocess.run(command.split())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Merge and subset Sentinel-1 SLC data.')
    parser.add_argument('--slc1_dir', type=str, required=True, help='Directory of the first set of SLC files')
    parser.add_argument('--slc2_dir', type=str, required=True, help='Directory of the second set of SLC files')
    parser.add_argument('--merged_file_dir', type=str, required=True, help='Directory to save merged SLC files')
    parser.add_argument('--bbox', type=float, nargs=4, required=True, help='Bounding box coordinates (min lon, min lat, max lon, max lat)')

    args = parser.parse_args()
    main(args.slc1_dir, args.slc2_dir, args.merged_file_dir, args.bbox)
