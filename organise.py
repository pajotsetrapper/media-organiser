import os, sys, shutil, hashlib
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
import ffmpeg

log_file = None
file_count = 0
duplicate_count = 0
potential_duplicate_count = 0

def _log(log_file, message):
    """Quick & dirty logger
    Args:
        log_file (string): fully qualified name of the file
        message (string): message to be logged
    """
    with open(log_file, 'a') as file:
            file.write(message)

def _get_exif(file_path):
    """_summary_

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        _type_: the exif data of the file
    """
    image = Image.open(file_path)
    image.verify()
    return image._getexif()

def _get_timestamp_from_exif(file_path):
    """Tries to obtain a timestamp from exif metadata available in a media (image) file.

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        string: raw timestamp ('DateTimeOriginal') from the Exif header or None
    """
    exif = _get_exif(file_path)
    for key, value in exif.items():
        name = TAGS.get(key, key)
        if name == 'DateTimeOriginal':
            return value

def _get_timestamp_from_video_metadata(file_path):
    """Tries to obtain a timestamp from metadata available in a media file.
    Requires ffmpeg to be installed & its path to be in the $PATH env variable of your OS.

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        string: raw timestamp obtained using ffmpeg
    """
    raw_timestamp = ffmpeg.probe(file_path)["streams"][0]["tags"]["creation_time"]
    return raw_timestamp

def get_timestamp_from_metadata(file_path):
    """Gets the timestamp from either the exif header in an image, or from  the header of a video file.

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        string: timestamp in format yyyy:mm:dd-hh:mm:ss
    """
    # TODO : add support for heic as well, may need to refactor to use pillow iso PIL
    image_extentions = ('.jpg', '.jpeg')
    ext = os.path.splitext(file_path)[1].lower()
    timestamp_raw = None
    timestamp_formatted = None
    try:
        if ext in image_extentions:
            timestamp_raw = _get_timestamp_from_exif(file_path)
            timestamp_formatted = timestamp_raw.replace(' ', '-')
        else:
            timestamp_raw = _get_timestamp_from_video_metadata(file_path)
            timestamp_formatted = timestamp_raw.split('.')[0].replace('-',':').replace('T','-')
    except Exception:
        pass # No timestamp available

    return timestamp_formatted

def exif_header_contains_geolocation(file_path):
    """Check if a file is geotagged

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        boolean: True if the file contains a geolocation, False otherwise
    """
    try:
        exif_data = _get_exif(file_path)
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                return True
    except Exception:
        pass
    return False

def has_same_hash(file1_path, file2_path):
    """_summary_

    Args:
        file1_path (string): fully qualified name of the file
        file2_path (string): fully qualified name of the file

    Returns:
        boolean: True if both files have the same md5 hash, False otherwise
    """
    with open(file1_path, 'rb') as f:
        file1_hash = hashlib.md5(f.read()).hexdigest()
    with open(file2_path, 'rb') as f:
        file2_hash = hashlib.md5(f.read()).hexdigest()
    return (file1_hash == file2_hash)

def has_similar_filesize(file1_path, file2_path, max_size_difference_bytes=8192):
    """Check if 2 sizes have similar filesize (configurable max delta)

    Args:
        file1_path (string): fully qualified name of the file
        file2_path (string): fully qualified name of the file
        max_size_difference_bytes (int, optional): max size difference, expressed in bytes. Defaults to 8192.

    Returns:
        boolean: True=similar size, False if file-sizes differ > max_size_difference_bytes
    """
    return ((abs(os.path.getsize(file1_path) - os.path.getsize(file2_path))) < max_size_difference_bytes)

def has_same_timestamp_in_metadata(file1_path, file2_path):
    """Check if 2 files have the same timestamp in their metadata

    Args:
        file1_path (string): fully qualified name of the file
        file2_path (string): fully qualified name of the file

    Returns:
        boolean: boolean indicating if the 2 files have the same timestamp in their metadata.
    """
    file1_timestamp = get_timestamp_from_metadata(file1_path)
    file2_timestamp = get_timestamp_from_metadata(file2_path)

    if ((file1_timestamp==None) or (file2_timestamp == None)):
        print ("  -> One of the timestamps is None -> return False")
        return False #There is no metadata, so cannot compare -> return False
    return file1_timestamp == file2_timestamp

def get_year_month_taken(file_path):
    """
    Get the year/month a media file was created.
    Timestamps are read from metadata (accurate), with fallback to file creation date.

    Args:
        file_path (string): fully qualified name of the file

    Returns:
        string: a (year, month) tuple of strings, where month has '-date-uncertain' appended in case there
        was no timestamp in the metadata.
    """
    year = None
    month = None
    timestamp = get_timestamp_from_metadata(file_path)

    if (timestamp is not None):
        year = timestamp.split(':')[0]
        month = timestamp.split(':')[1]
        return (year, month)
    else:
        #Could not get a timestamp in the metadata, fallback to file creation date:
        date_time_file_creation = datetime.fromtimestamp(os.path.getmtime(file_path))
        year = date_time_file_creation.strftime("%Y")
        month = date_time_file_creation.strftime("%m")
        return (year, month + "-date-uncertain")

def smart_copy(file_path, target_folder):
    """Copy the file 'file_path' to the target folder in a smart way to detect / handle (near)duplicates:
    - File with same name & hash exists in target folder -> skip
    - File with same name & different hash exists:
        - Same timestamp in metadata & file-size nearly identical (typically only metadata is different):
            - Skip, unless the source file additionally contains gps data (replace in the latter case)
        - No (or different) timestamp in metadata, file-size nearly identical
            - Copy the file to target folder, adding a suffix "_ud#", indicating it possibly is a duplicate
        - Otherwise, copy the file to target with a suffic "u#" (# being a number)

    Args:
        file_path (_type_): _description_
        target_folder (_type_): _description_

    Returns:
        None: nada
    """
    global log_file
    global duplicate_count
    global potential_duplicate_count
    file_name = os.path.basename(file_path)
    target_file_path = os.path.join(target_folder, file_name)

    if not os.path.exists(target_file_path):
        shutil.copy(file_path, target_file_path)
        return #done

    if has_same_hash(file_path, target_file_path): #Same has, file that exists in target is identical => don't copy
        duplicate_count += 1
        _log(log_file, "Duplicate with same hash;{};{};skipped\n".format(file_name, target_folder))
        return

    #Hash if different, but media file could still be duplicate aside from metadata => doing some more checks / adding some suffixes to facilitate triage
    suffix="_u"
    if (has_same_timestamp_in_metadata(file_path, target_file_path) and has_similar_filesize(file_path, target_file_path)):
        duplicate_count += 1
        #Exact same timestamp in exif & very similar file-size
        # -> must be a duplicate except for metadata (e.g. face-tags, geotag))
        # -> ensuring to keep the file with geolocation data only

        if exif_header_contains_geolocation(target_file_path):
            _log(log_file, "Suspecting duplicate with high certainty - same exif timestamp & similar size. Target already has gps data;{};{};skipped\n".format(file_name, target_folder))
            return
        else:
            if exif_header_contains_geolocation(file_path):
                with open(log_file, 'a') as file:
                    file.write("Suspecting duplicate with high certainty - same exif timestamp & similar size. Overwriting target as source additionally has GPS data;{};{};replaced\n".format(file_name, target_folder))
                shutil.copy(file_path, target_file_path)
                return
        return #Don't omit this!
    else:
        if has_similar_filesize(file_path, target_file_path):
            potential_duplicate_count+=1
            suffix+="d" #Flags a file as being potentially being a duplicate
    suffix += str(potential_duplicate_count)
    fn, ext = os.path.splitext(file_name)
    new_filename = fn + suffix + ext
    new_target_file_path = os.path.join(target_folder, new_filename)
    shutil.copy(file_path, new_target_file_path)
    _log(log_file, "Identical name, different hash;{};{};copied with suffix\n".format(file_name, new_target_file_path))


def organise(source_folder, organised_folder):
    global file_count
    for subdir, dirs, files in os.walk(source_folder):
        for file in files:
            file_count+=1
            file_path = os.path.join(subdir, file)
            (year_folder, month_folder) = get_year_month_taken(file_path)
            if (file.lower().endswith(".jpg")):
                print("P", end="")
                destination_folder = os.path.join(organised_folder, year_folder, "photos", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                smart_copy(file_path, destination_folder)

            else: #Also copy over non-jpg files (video etc)
                print("M", end="")
                year_folder, month_folder = get_year_month_taken(file_path)
                destination_folder = os.path.join(organised_folder, year_folder , "movies", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                smart_copy(file_path, destination_folder)

if __name__ == "__main__":
    #test()
    source_folder = sys.argv[1]
    destination_folder = sys.argv[2]
    if not os.path.exists(source_folder):
        print ("Folder {} does not exist, exiting".format(source_folder))
        sys.exit(-1)
    if not os.path.exists(destination_folder):
        try:
            os.makedirs(destination_folder)
        except:
            print ("Problem creating destination folder {}, exiting".format(source_folder))
            sys.exit(-1)

    log_file = os.path.join(destination_folder, "media-organiser.log")
    _log(log_file, "Brought some structure in {}\n".format(source_folder))
    organise(source_folder, destination_folder)
    _log(log_file, "# files processed: {}".format(file_count))
    _log(log_file, "\n# duplicate files: {}".format(duplicate_count))
    _log(log_file, "\n# potentially duplicate files: {}".format(potential_duplicate_count))
