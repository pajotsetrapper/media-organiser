import os
import sys
import shutil
import hashlib
import subprocess
import ffmpeg
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS

logFile = None
duplicateNameDifferentHashCount = 0
duplicateFileCount = 0
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
        exif = get_exif(filename)
        for key, value in exif.items():
            name = TAGS.get(key, key)
            if name == 'DateTimeOriginal':            
                year = value.split(':')[0]
                month = value.split(':')[1]
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

def move_file(file_path, target_folder):
    global duplicateNameDifferentHashCount
    global duplicateFileCount
    global logFile
    file_name = os.path.basename(file_path)
    target_file_path = os.path.join(target_folder, file_name)
    if not os.path.exists(target_file_path):
        shutil.copy(file_path, target_file_path)
    else:        
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        with open(target_file_path, 'rb') as f:
            target_file_hash = hashlib.md5(f.read()).hexdigest()
        if file_hash != target_file_hash:          
            fn, ext = os.path.splitext(file_name)
            newFn = fn + "u" + str(duplicateNameDifferentHashCount) + ext #add a "u" as suffix, with a counter to avoid clash & to give it a unique name
            duplicateNameDifferentHashCount+=1
            new_target_file_path = os.path.join(target_folder, newFn)
            shutil.copy(file_path, new_target_file_path)
            with open(logFile, 'a') as file:
                file.write("Identical name, different hash: {} copied to {}.\n".format(file_name, new_target_file_path))
        else:
            with open(logFile, 'a') as file:
                file.write("Duplicate: {} already exists in {} with same hash -> discarded\n".format(file_name, target_folder))
            duplicateFileCount+=1
        

def organise(root_folder):
    global files_processed
    global images_processed
    global others_processed
    global logFile
    
    print (root_folder)
    #organised_folder = root_folder + "-organised"
    organised_folder = "Z:\\fotos-video-organised"
    
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
                images_processed+=1                
                destination_folder = os.path.join(organised_folder, year_folder, "photos", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                print("P", end="")
                move_file(file_path, destination_folder)
                      
            else: #Also copy over non-jpg files (video etc)
                others_processed+=1                
                year_folder, month_folder = get_year_month_taken(file_path)
                destination_folder = os.path.join(organised_folder, year_folder , "movies", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                print("M", end="")
                move_file(file_path, destination_folder)
             
if __name__ == "__main__":
    rootFolder = sys.argv[1]    
    if os.path.exists(rootFolder):
        organise(rootFolder)
        with open(logFile, 'a') as file:                        
                file.write("# files processed: {}".format(files_processed))
                file.write("\n#   -> images: {}".format(images_processed))
                file.write("\n#   -> other: {}".format(others_processed))
                file.write("\n# duplicate files: {}".format(duplicateFileCount))
                file.write("\n# renamed files (same hash & filename): {}".format(duplicateNameDifferentHashCount))
    else:
        print ("Folder {} does not exist, exiting".format(rootFolder))
        
