import os
import sys
import shutil
import hashlib
import subprocess
import ffmpeg
from datetime import datetime
from PIL import Image, ExifTags
from PIL.ExifTags import TAGS

logFile = None
duplicateNameDifferentHashCount = 0
duplicateFileCount = 0
potentialDuplicateFileCountSameTimestampSimilarSize = 0
potentialDuplicateFileCount = 0 #Same filename, different hash but filesize deviates max 4kb
files_processed = 0
images_processed = 0
others_processed = 0

def get_exif(filename):
    """
    Returns the exif header of a media file
    """
    image = Image.open(filename)
    image.verify()
    return image._getexif()

def getDateTimeOrginalFromExif(file_path):
    exif = get_exif(file_path)
    for key, value in exif.items():
        name = TAGS.get(key, key)
        if name == 'DateTimeOriginal':
            return value

def hasGpsDataInExif(file_path):
    try:
        image = Image.open(file_path)
        exif_data = image.getexif()
        for tag_id in exif_data:
            tag = TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                return True
    except:
        pass
    return False

def has_similar_filesize(file1_path, file2_path):
    """
    This method uses the os.path.getsize() function to get the size of each file in bytes and then compares the difference between them to 4KB (4096 bytes).
    If the difference is less than 4KB, it returns True; otherwise, it returns False.
    Using this to mark images with same filename & size difference <4kb as being duplicates potentially
    """
    if (abs(os.path.getsize(file1_path) - os.path.getsize(file2_path)) < 8192):
        print("\nFile size difference between 2 images < 8192 bytes")
        return True
    else:
        print("\nFile size difference between 2 images > 8192 bytes, more than header must be different")
        return False

def has_same_datetime_in_exif(photo1_path, photo2_path):
    print("\nChecking if {} and {} have a similar size".format(photo1_path, photo2_path))
    try:
        exifDateTime1 = getDateTimeOrginalFromExif(photo1_path)
        exifDateTime2 = getDateTimeOrginalFromExif(photo2_path)
        if date_time1 == date_time2:
            print("\nSame date/time in exif for {}-{}".format(photo1_path, photo2_path))
        return date_time1 == date_time2
    except:
        print("\n---> Not an image -> Could not parse exif")
        return False

def get_year_month_taken(filename):
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
        exifDateTime = getDateTimeOrginalFromExif(filename)
        year = exifDateTime.split(':')[0]
        month = exifDateTime.split(':')[1]
        return (year, month)
    except:
        pass

    #No exif header with date found, try getting created date using ffmpeg
    #uses ffprobe command to extract all possible metadata from the media file
    try:
        #Requires ffmpeg to be installed & its bin folder to be part of the $PATH
        creationTime = ffmpeg.probe(filename)["streams"][0]["tags"]["creation_time"].split("-")
        year = creationTime[0]
        month = creationTime[1]
        return (year, month)
    except:
        pass

    #Could not get the creation month from exif or video header, use file creation date:
    date_created = datetime.fromtimestamp(os.path.getmtime(filename))
    year = date_created.strftime("%Y")
    month = date_created.strftime("%m")
    return (year, month + "-date-uncertain")

def smart_copy(file_path, target_folder):
    global duplicateNameDifferentHashCount
    global duplicateFileCount
    global potentialDuplicateFileCountSameTimestampSimilarSize
    global potentialDuplicateFileCount
    global logFile
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
            with open(logFile, 'a') as file:
                file.write("Duplicate with same hash;{};{};skipped\n".format(file_name, target_folder))
            duplicateFileCount+=1
            return

        else: #Doing some more checks / adding some suffixes to facilitate triage
            duplicateNameDifferentHashCount+=1
            suffix="_u"

            if (has_same_datetime_in_exif(file_path, target_file_path) and has_similar_filesize(file_path, target_file_path)):
                #Exact same timestamp in exif & very similat file-size -> must be a duplicate as well (with some header information altered (e.g. face-tags, geotag))
                #Ensuring to keep the file with geolocation data
                potentialDuplicateFileCountSameTimestampSimilarSize+=1
                if hasGpsDataInExif(target_file_path):
                    with open(logFile, 'a') as file:
                        file.write("Suspecting duplicate with high certainty - same exif timestamp & similar size. Target already has gps data;{};{};skipped\n".format(file_name, target_folder))
                    return
                else:
                    if hasGpsDataInExif(file_path):
                        with open(logFile, 'a') as file:
                            file.write("Suspecting duplicate with high certainty - same exif timestamp & similar size. Overwriting target as source additionally has GPS data;{};{};replaced\n".format(file_name, target_folder))
                        shutil.copy(file_path, target_file_path)
                        return

            else:
                if has_similar_filesize(file_path, target_file_path):
                    suffix+="d" #Flags a file as being potentially being a duplicate
                    potentialDuplicateFileCount+=1
            suffix += str(potentialDuplicateFileCount)
            fn, ext = os.path.splitext(file_name)
            newFn = fn + suffix + ext
            new_target_file_path = os.path.join(target_folder, newFn)
            shutil.copy(file_path, new_target_file_path)
            with open(logFile, 'a') as file:
                file.write("Identical name, different hash;{};{};copied with suffix\n".format(file_name, new_target_file_path))


def organise(root_folder):
    global files_processed
    global images_processed
    global others_processed
    global logFile

    print(root_folder)
    #organised_folder = root_folder + "-organised"
    organised_folder = "G:\\2013-fotos-video-organised"

    if not os.path.exists(organised_folder):
        os.makedirs(organised_folder)
    logFile = os.path.join(organised_folder, "media-organiser.log")
    with open(logFile, 'a') as file:
        file.write("Brought some structure in {}\n".format(root_folder))

    for subdir, dirs, files in os.walk(root_folder):
        for file in files:
            files_processed+=1
            file_path = os.path.join(subdir, file)
            (year_folder, month_folder) = get_year_month_taken(file_path)
            if (file.lower().endswith(".jpg")):
                print("P", end="")
                images_processed+=1
                destination_folder = os.path.join(organised_folder, year_folder, "photos", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                smart_copy(file_path, destination_folder)

            else: #Also copy over non-jpg files (video etc)
                print("M", end="")
                others_processed+=1
                year_folder, month_folder = get_year_month_taken(file_path)
                destination_folder = os.path.join(organised_folder, year_folder , "movies", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                smart_copy(file_path, destination_folder)

if __name__ == "__main__":
    rootFolder = sys.argv[1]
    if os.path.exists(rootFolder):
        organise(rootFolder)
        with open(logFile, 'a') as file:
                file.write("# files processed: {}".format(files_processed))
                file.write("\n#   -> images: {}".format(images_processed))
                file.write("\n#   -> other: {}".format(others_processed))
                file.write("\n# duplicate files: {}".format(duplicateFileCount))
                file.write("\n# nearly identical files, sufficently identical to skip/replace: {}".format(potentialDuplicateFileCountSameTimestampSimilarSize))
                file.write("\n# renamed files (same hash & filename): {}".format(duplicateNameDifferentHashCount))
    else:
        print ("Folder {} does not exist, exiting".format(rootFolder))
