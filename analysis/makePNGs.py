import os
import subprocess
import pdb
import glob
from analysis import generateGnuplotFile

"""
    Instructions:
        Keys in "folders", "titles" and "outputFilenames" should match (could be avoided with simple refactor...)
        Keys are: "#steps_#processors", #steps is important for the plots

        Change params to match simulation.
"""

folders = {"8_16":"3ptb_8_16", "8_32":"3ptb_8_32", "8_64":"3ptb_8_64", "8_128":"3ptb_8_128",\
           "4_16":"3ptb_4_16", "4_32":"3ptb_4_32", "4_64":"3ptb_4_64", "4_128":"3ptb_4_128"}

subfoldersWildcard = "inversely_*"

titles = {"8_16":"n=16, 8 steps, %s", "8_32":"n=32, 8 steps, %s", "8_64":"n=64, 8 steps, %s", "8_128":"n = 128, 8 steps, %s",\
           "4_16":"n=16, 4 steps, %s", "4_32":"n=32, 4 steps, %s", "4_64":"n=64, 4 steps, %s", "4_128":"n=128, 4 steps, %s"}

outputFilenames = {"8_16":"16_8_%s", "8_32":"32_8_%s", "8_64":"64_8_%s", "8_128":"128_8_%s",\
           "4_16":"16_4_%s", "4_32":"32_4_%s", "4_64":"64_4_%s", "4_128":"128_4_%s"}

params = {"stepsCol" : 2,
        "RMSDCol" : 5,
        "BECol" : 6,
        "reportFilename" : "report_"}


gplFolder = "/gpfs/scratch/bsc72/bsc72755/adaptiveSampling/simulations"
tmpFolder = "/tmp"

tmpPlotFile = os.path.join(tmpFolder, "tmp.gpl")

gnuplot = "$SCRATCH/software/gnuplot/bin/gnuplot"


def buildGnuplotString(title, outputFilename, params):
    gnuplotFileStringContent = """\
    set term png\n\
    set title "%(plotTitle)s"\n\
    set output "rmsd_steps_%(outputFilename)s.png"\n\
    %(rmsdStepsPringString)s\n\
    \n\
    set output "be_rmsd_%(outputFilename)s.png\n\
    %(beRmsdPrintString)s\n
    """

    stepsPerRun = params["stepsPerRun"]
    stepsCol = params["stepsCol"]
    RMSDCol = params["RMSDCol"]
    BECol = params["BECol"]
    reportFilename = params["reportFilename"]

    rmsdStepsPrintString = generateGnuplotFile.generatePrintString(stepsPerRun, stepsCol, RMSDCol, reportFilename, "PRINT_RMSD_STEPS")
    beRmsdPrintString = generateGnuplotFile.generatePrintString(stepsPerRun, RMSDCol, BECol, reportFilename, "PRINT_BE_RMSD")
    dictionary = {"plotTitle":title,
                    "outputFilename":outputFilename,
                    "rmsdStepsPringString":rmsdStepsPrintString,
                    "beRmsdPrintString":beRmsdPrintString}

    return gnuplotFileStringContent%dictionary


for key, folder in folders.iteritems():
    print "Folder: ", folder
    try:
        os.chdir(folder)
    except:
        continue

    params["stepsPerRun"] = int(key.split("_")[0])

    subfolders = glob.glob(subfoldersWildcard)
    for subfolder in subfolders:
        os.chdir(subfolder)

        gnuplotFileContent = buildGnuplotString(titles[key]%subfolder, outputFilenames[key]%subfolder, params)

        with open(tmpPlotFile, "w") as f:
            f.write(gnuplotFileContent)

        proc = subprocess.Popen("%s %s"%(gnuplot, tmpPlotFile), stdout=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()
        if out: print out
        if err: print err
        os.chdir("..")

    os.chdir("..")