import os
import glob
import pyproj
import rasterio
import geopandas as gpd
import numpy as np
from shapely.geometry import box
from rasterio.transform import Affine
import rasterio.mask

dir_input = r'C:\download_hls'
dir_output = r'C:\tutorial'
# Define an interest region as a bounding box in the format (left, bottom, right, top)
xmin, ymin, xmax, ymax = -90.325140990174, 33.512384999302, -90.384131632179, 33.557031208366
evi_img = glob.glob(os.path.join(dir_input, 'T15SYT', 'spectral_indexes','**', '*evi*.tif'), recursive=True)

base_dates = []
for dates in evi_img:
    dates = os.path.basename(dates).split('_')[0].split('T')[0]
    formatted_date = f"{dates[:4]}-{dates[4:6]}-{dates[6:]}"
    base_dates.append(formatted_date)


def reproject_coords(input_raster, xmin, ymin, xmax=None, ymax=None):
    with rasterio.open(input_raster) as src:
        proj = src.crs.to_epsg()
    original_proj = pyproj.CRS("EPSG:4326")
    target_proj = pyproj.CRS("EPSG:" + str(proj))
    transformer = pyproj.Transformer.from_crs(original_proj, target_proj, always_xy=True)
    if xmax is not None and ymax is not None:
        minx, miny = transformer.transform(xmin, ymin)
        maxx, maxy = transformer.transform(xmax, ymax)
        return minx, miny, maxx, maxy
    else:
        minx, miny = transformer.transform(xmin, ymin)
        return minx, miny


def export_raster(output_filepath, raster_data, height, width, dtype, transform, crs, nodata=0):
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    with rasterio.open(output_filepath, "w", driver="GTiff",
                       height=height, width=width,
                       count=raster_data.shape[0],  # Set the count to the number of bands
                       dtype=dtype,
                       transform=transform, crs=crs,
                       nodata=nodata) as dst:
        for band_idx in range(raster_data.shape[0]):
            dst.write(raster_data[band_idx, :, :], band_idx + 1)  # Write each band separately


# Reproject the coordinates from WG84 to UTM
coords_preproj = reproject_coords(evi_img[0], xmin, ymin, xmax, ymax)

with rasterio.open(evi_img[0]) as src:
    proj = src.profile['crs']

# Build a geodaframe using geopandas for an interest region
interest_region = gpd.GeoDataFrame(geometry=[box(coords_preproj[0], coords_preproj[1], coords_preproj[2],
                                                 coords_preproj[3])], crs=proj)
# Code for clipping and stacking rasters
clip_raster = []
for evi_raster in evi_img:
    print(evi_raster)
    with rasterio.open(evi_raster) as src:
        # Clip the raster to the extent of the bounding box
        clipped, _ = rasterio.mask.mask(src, [interest_region.geometry.values[0]], crop=True)
        # Replace NaN values with NaN and leave other values unchanged
        clipped = np.nan_to_num(clipped, nan=np.nan)
        clipped = np.where(clipped == 0, np.nan, clipped)
        clipped = clipped[:, :, 1:]
        clipped = clipped[:, :-1]
        clip_raster.append(clipped)

# Get the bounding box coordinates of the interest region
x_min, y_min, x_max, y_max = interest_region.total_bounds

# Open the original raster to obtain the spatial reference and coordinate system
with rasterio.open(evi_img[0]) as orig_ds:
    # Get the spatial reference and coordinate system from the original raster
    crs = orig_ds.crs
    width = int((x_max - x_min) / orig_ds.transform[0])
    height = int((y_max - y_min) / orig_ds.transform[0])
    pixel_width = orig_ds.transform[0]
    pixel_height = orig_ds.transform[0]

# Create the transform using the origin, pixel width, and pixel height from the interest region
transform = Affine(pixel_width, 0, x_min, 0, -pixel_height, y_max)

# Save clip raster
for layer_idx, (layer_data, current_date) in enumerate(zip(clip_raster, base_dates)):
    # Construct the output file path for the current layer
    basedir_evi = os.path.join(dir_output, "evi_clip")
    dir_output_date = os.path.join(basedir_evi)
    os.makedirs(dir_output_date, exist_ok=True)
    output_filepath = os.path.join(dir_output_date, f"evi_{current_date}.tif")
    export_raster(output_filepath, layer_data, height, width, layer_data.dtype, transform, crs)
    print(layer_idx)
