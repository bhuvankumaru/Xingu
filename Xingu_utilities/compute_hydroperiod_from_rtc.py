import numpy as np
import rasterio
from rasterio.enums import Resampling
from scipy.stats import norm
from skimage.filters import threshold_otsu
import os
import glob
import argparse
from rasterio.warp import calculate_default_transform, reproject

def resample_water_frequency(waterFreq_raster_file, sample_rtc_file):
    with rasterio.open(sample_rtc_file) as src_rtc:
        rtc_data = src_rtc.read(1)  # Assuming single band data
        rtc_profile = src_rtc.profile
        rtc_crs = src_rtc.crs
        rtc_transform = src_rtc.transform
        rtc_width = src_rtc.width
        rtc_height = src_rtc.height

    with rasterio.open(waterFreq_raster_file) as src_waterFreq:
        # Calculate the transform for the resampled data
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_waterFreq.crs, rtc_crs, src_waterFreq.width, src_waterFreq.height, *src_waterFreq.bounds, 
            dst_width=rtc_width, dst_height=rtc_height, resolution=None
        )

        # Create an empty array to store the resampled data
        waterFreq = np.empty((rtc_height, rtc_width), dtype=src_waterFreq.dtypes[0])

        # Perform the resampling
        reproject(
            source=rasterio.band(src_waterFreq, 1),
            destination=waterFreq,
            src_transform=src_waterFreq.transform,
            src_crs=src_waterFreq.crs,
            dst_transform=dst_transform,
            dst_crs=rtc_crs,
            resampling=Resampling.nearest  # Adjust as needed
        )

    return waterFreq, rtc_transform, rtc_crs, rtc_profile

def get_land_water_mask_otsu(rtc_data, waterFreq, max_freq, min_freq):
    # Apply mask to extract backscatter values
    mask = (waterFreq >= max_freq) & (rtc_data>-50);
    backscatter_values = rtc_data[mask]
    backscatter_values = backscatter_values[backscatter_values < 0]

    mu1, std1 = norm.fit(backscatter_values.flatten());otsu_threshold = mu1+(2*std1);#otsu_threshold = threshold_otsu(backscatter_values)

    # Apply Otsu's threshold to create a binary mask
    binary_mask = rtc_data < otsu_threshold
    binary_mask = binary_mask.astype(int)
    binary_mask[rtc_data == -9999] = -9999

    return binary_mask, otsu_threshold

def compute_hydroperiod(time_series_paths, waterFreq, max_freq=50, min_freq=1):
    hydroperiods = [];dates=[];

    for image_path in time_series_paths:
        with rasterio.open(image_path) as src:
            print(image_path);dates.append(os.path.basename(image_path)[7:15]);image_array = src.read(1)
            land_water_mask, otsu_threshold = get_land_water_mask_otsu(image_array, waterFreq, max_freq, min_freq)
            hydroperiods.append(land_water_mask)

    # Sum the hydroperiods across the time series
    aggregated_hydroperiod = np.sum(hydroperiods, axis=0)
    # Normalize hydroperiod values (optional)
    hydroperiod = aggregated_hydroperiod / len(hydroperiods);hydroperiod[hydroperiod < 0] = -9999

    return hydroperiod,dates

def save_hydroperiod(hydroperiod, transform, crs, profile, output_path,metadata):
    profile.update(dtype=rasterio.float32, count=1, compress='lzw', transform=transform)
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(hydroperiod.astype(rasterio.float32), 1);dst.update_tags(**metadata);
        dst.crs = crs

def main(timeseries_file_dir, waterFreq_raster_file, year, output_file):
    # Find the first raster file in the time series directory for the specified year as the sample RTC file
    sample_rtc_file = sorted(glob.glob(os.path.join(timeseries_file_dir, f'subset_{year}*_VV.tif')))[0]

    waterFreq, rtc_transform, rtc_crs, rtc_profile = resample_water_frequency(waterFreq_raster_file, sample_rtc_file)

    time_series_paths = sorted(glob.glob(os.path.join(timeseries_file_dir, f'subset_{year}*_VV.tif')))
    hydroperiod,dates = compute_hydroperiod(time_series_paths, waterFreq);metadata={};metadata['dates'] = ','.join(dates);

    # Save the hydroperiod raster
    save_hydroperiod(hydroperiod, rtc_transform, rtc_crs, rtc_profile, output_file,metadata)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute hydroperiod from Sentinel-1 RTC images.')
    parser.add_argument('--timeseries_file_dir', type=str, required=True, help='Directory containing time series RTC files')
    parser.add_argument('--waterFreq_raster_file', type=str, required=True, help='Path to water frequency raster file')
    parser.add_argument('--year', type=int, required=True, help='Year for which hydroperiod is to be computed')
    parser.add_argument('--output_file', type=str, help='Output hydroperiod file name')

    args = parser.parse_args()
    
    if args.output_file is None:
        output_file = f'hydroperiod_{args.year}.tif'
    else:
        output_file = args.output_file
    
    main(args.timeseries_file_dir, args.waterFreq_raster_file, args.year, output_file)

