import os, sys, shutil, hashlib
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
import ffmpeg

logFile = None

file_count = 0
duplicate_count = 0
potential_duplicate_count = 0

"""Returns the exif header of an image file
@param file_path: fully qualified path name
@raise Exception: wildcard exception
"""
def get_exif(file_path):
    image = Image.open(file_path)
    image.verify()
    return image._getexif()

def get_timestamp_from_exif(file_path):
    exif = get_exif(file_path)
    for key, value in exif.items():
        name = TAGS.get(key, key)
        if name == 'DateTimeOriginal':
            return value
        
def get_timestamp_from_video_metadata(file_path):
    #Requires ffmpeg to be installed & its bin folder to be part of the $PATH
    date_time_filmed = ffmpeg.probe(file_path)["streams"][0]["tags"]["creation_time"]
    return date_time_filmed

def exif_header_contains_geolocation(file_path):
    try:
        exif_data = get_exif(file_path)
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                return True
    except:
        pass
    return False


def has_similar_filesize(file1_path, file2_path, max_size_difference_bytes=8192):
    """
    This method uses the os.path.getsize() function to get the size of each file in bytes and then compares the difference between them.
    If the difference is less than max_size_difference_bytes bytes, it returns True; otherwise, it returns False.
    Using this to mark images with same filename & size difference <4kb as being duplicates potentially
    """
    return ((abs(os.path.getsize(file1_path) - os.path.getsize(file2_path))) < max_size_difference_bytes)        

def has_same_datetime_in_exif(file1_path, file2_path):
    print("\nChecking if {} and {} have the same date/time in exif".format(file1_path, file2_path))
    try:
        exif_date_time_1 = get_timestamp_from_exif(file1_path)
        exif_date_time_2 = get_timestamp_from_exif(file2_path)
        if exif_date_time_1 == exif_date_time_2:
            print("\nSame date/time in exif for {}-{}".format(file1_path, file2_path))
        return exif_date_time_1 == exif_date_time_2
    except:
        #TODO - as backup - check for video's here as well - using ffprobe?
        return False

def get_year_month_taken(file_path):
    """
    Returns a (year, month) tuple with the year/month the media file was created. Obtaining this info
    in the following order of attempts
    1/ Reading exif header
    2/ Using ffprobe to get the this date
    3/ As fallback, taking the created date of the file itself
    @param: filename complete path to the media files you want to get the created date for
    """
    year = None
    month = None
    #1st attempt, get the exif header & parse DateTimeOriginal
    try:
        date_time_taken = get_timestamp_from_exif(file_path)
        year = date_time_taken.split(':')[0]
        month = date_time_taken.split(':')[1]
        return (year, month)
    except:
        pass

    #No exif header with date found, try getting created date using ffmpeg
    #uses ffprobe command to extract all possible metadata from the media file
    try:        
        date_time_filmed = get_timestamp_from_video_metadata(file_path)        
        year = date_time_filmed.split("-")[0]
        month = date_time_filmed.split("-")[1]
        return (year, month)
    except:
        pass

    #Could not get the creation month from exif or video header, use file creation date:
    date_time_file_creation = datetime.fromtimestamp(os.path.getmtime(file_path))
    year = date_time_file_creation.strftime("%Y")
    month = date_time_file_creation.strftime("%m")
    return (year, month + "-date-uncertain")

def smart_copy(file_path, target_folder):    
    global logFile
    global duplicate_count
    global potential_duplicate_count
    file_name = os.path.basename(file_path)
    target_file_path = os.path.join(target_folder, file_name)

    if not os.path.exists(target_file_path):
        shutil.copy(file_path, target_file_path)

    else: # A file with the same name already exists in destination
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        with open(target_file_path, 'rb') as f:
            target_file_hash = hashlib.md5(f.read()).hexdigest()

        if file_hash == target_file_hash: #Same has, file that exists in target is identical => don't copy
            duplicate_count += 1
            with open(logFile, 'a') as file:                
                file.write("Duplicate with same hash;{};{};skipped\n".format(file_name, target_folder))
            return

        else: #Doing some more checks / adding some suffixes to facilitate triage
            suffix="_u"
            if (has_same_datetime_in_exif(file_path, target_file_path) and has_similar_filesize(file_path, target_file_path)):
                duplicate_count += 1
                #Exact same timestamp in exif & very similat file-size -> must be a duplicate as well (with some header information altered (e.g. face-tags, geotag))
                #Ensuring to keep the file with geolocation data
                
                if exif_header_contains_geolocation(target_file_path):
                    with open(logFile, 'a') as file:
                        file.write("Suspecting duplicate with high certainty - same exif timestamp & similar size. Target already has gps data;{};{};skipped\n".format(file_name, target_folder))
                    return
                else:
                    if exif_header_contains_geolocation(file_path):
                        with open(logFile, 'a') as file:
                            file.write("Suspecting duplicate with high certainty - same exif timestamp & similar size. Overwriting target as source additionally has GPS data;{};{};replaced\n".format(file_name, target_folder))
                        shutil.copy(file_path, target_file_path)
                        return

            else:
                if has_similar_filesize(file_path, target_file_path):
                    potential_duplicate_count+=1
                    suffix+="d" #Flags a file as being potentially being a duplicate                    
            suffix += str(potential_duplicate_count)
            fn, ext = os.path.splitext(file_name)
            newFn = fn + suffix + ext
            new_target_file_path = os.path.join(target_folder, newFn)
            shutil.copy(file_path, new_target_file_path)
            with open(logFile, 'a') as file:
                file.write("Identical name, different hash;{};{};copied with suffix\n".format(file_name, new_target_file_path))


def organise(root_folder):
    global logFile
    global file_count
    global duplicate_count
    global potential_duplicate_count
    image_file_extensions = ('jpg', 'jpeg', 'heic')

    print(root_folder)
    organised_folder = "G:\\2013-fotos-video-organised"

    if not os.path.exists(organised_folder):
        os.makedirs(organised_folder)
    logFile = os.path.join(organised_folder, "media-organiser.log")
    with open(logFile, 'a') as file:
        file.write("Brought some structure in {}\n".format(root_folder))

    for subdir, dirs, files in os.walk(root_folder):
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

    #print(exif_header_contains_geolocation("G:\\2013-fotos-video-organised\\2013\\photos\\08\\IMG_4817.JPG"))
    #print(exif_header_contains_geolocation("G:\\2013-fotos-video-organised\\2013\\photos\\08\\IMG_4817_ud486.JPG"))
    #print (has_same_datetime_in_exif("G:\\2013-fotos-video-organised\\2013\photos\\08\\IMG_4842.JPG", "D:/02-foto/Sorting/Album-2013/sorteren/118___08/IMG_4842.JPG"))
    #print (has_same_datetime_in_exif("G:\\2013-fotos-video-organised\\2013\photos\\08\\IMG_4842.JPG", "D:/02-foto/Sorting/Album-2013/sorteren/118___08/IMG_4840.JPG"))

    rootFolder = sys.argv[1]
    if os.path.exists(rootFolder):
        organise(rootFolder)
        with open(logFile, 'a') as file:
                file.write("# files processed: {}".format(file_count))
                file.write("\n# duplicate files: {}".format(duplicate_count))
                file.write("\n# potentially duplicate files: {}".format(potential_duplicate_count))
    else:
        print ("Folder {} does not exist, exiting".format(rootFolder))