import pickle
import numpy as np
import matplotlib.pyplot as plt
from atomset import atomset
from mpl_toolkits.mplot3d import Axes3D
import pdb as debug


def extractCOMMatrix(clusters, resname):
    n = len(clusters)
    cluster_matrix = np.zeros((n, 3))
    metrics = np.zeros(n)
    population = np.zeros(n)
    total_elements = 0
    contacts = np.zeros(n)
    for index, cluster in enumerate(clusters):
        metrics[index] = cluster.metric
        contacts[index] = cluster.contacts
        ligandPDB = atomset.PDB()
        ligandPDB.initialise(cluster.pdb.pdb, resname=resname)
        cluster_matrix[index, :] = ligandPDB.extractCOM()
        population[index] = cluster.elements
        total_elements += cluster.elements
    return cluster_matrix, metrics, total_elements, population, contacts


def plotClusters2D(cluster_matrix, metrics, title):
    ccx = cluster_matrix[:, 0]
    ccy = cluster_matrix[:, 1]
    ccz = cluster_matrix[:, 2]
    fig, axes = plt.subplots(nrows=2, ncols=2, sharex='col',
                             sharey='row')
    fig.suptitle(title)
    scatter1 = axes[0][0].scatter(ccx, ccy, c=metrics)  # ,label="Set %d"%index)
    axes[0][1].scatter(ccz, ccy, c=metrics)  # ,label="Set %d"%index)
    axes[1][0].scatter(ccx, ccz, c=metrics)  # ,label="Set %d"%index)
    fig.colorbar(scatter1)

#    axes[1][0].legend(loc='center right', bbox_to_anchor=[1.8,0.5])
    axes[0][0].set_ylabel('y')
    axes[1][0].set_ylabel('z')
    axes[1][0].set_xlabel('x')
    axes[1][1].axis('off')
    axes[0][1].set_xticks(axes[1][1].get_xticks())
    axes[0][1].set_xticklabels(axes[1][1].get_xticklabels())
    axes[0][1].set_xlabel('z')
    return fig


def plotClusters(cluster_matrix, metrics, title):
    fig = plt.figure()
    ax = Axes3D(fig)
    ccx = cluster_matrix[:, 0]
    ccy = cluster_matrix[:, 1]
    ccz = cluster_matrix[:, 2]
    print title
    print ccx.size
    fig.suptitle(title)
    scatter1 = ax.scatter(ccx, ccy, zs=ccz, c=metrics)
    fig.colorbar(scatter1)
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_xlabel('x')
    return fig


def plotClusteringData(pklObjectFilename, resname, titlemetric, titlepopulation,
                       titlecontacts, metricPlotFilename="",
                       populationPlotFilename="", contactsPlotFilename=""):

    with open(pklObjectFilename, "r") as f:
        clObject = pickle.load(f)

    comCoord, metrics, totalElements, population, contacts = extractCOMMatrix(clObject.clusters.clusters, resname)

    plot = plotClusters(comCoord, metrics, titlemetric)
    if metricPlotFilename:
        plot.savefig(metricPlotFilename)

    plotContpop = plotClusters(comCoord, population, titlepopulation)
    if populationPlotFilename:
        plotContpop.savefig(populationPlotFilename)

    plotContcont = plotClusters(comCoord, contacts, titlecontacts)
    if contactsPlotFilename:
        plotContcont.savefig(contactsPlotFilename)

    print "Number of elements", totalElements

if __name__ == "__main__":
    resname = "ALJ"

    # Cont
    pklObjectFilename = "ClCont.pkl"
    metricPlotFilename = ""  # "results/contactClusters.png"
    populationPlotFilename = ""  # "results/contactClusterspop.png"
    contactsPlotFilename = ""  # "results/contactClustersContacts.png"
    titlemetric = "Metrics Contacts"
    titlepopulation = "Population Contacts"
    titlecontacts = "Number of contacts Contacts"

    plotClusteringData(pklObjectFilename, resname, titlemetric, titlepopulation,
                       titlecontacts, metricPlotFilename,
                       populationPlotFilename, contactsPlotFilename)

    # Acc
    pklObjectFilename = "ClAcc.pkl"
    metricPlotFilename = "results/metricplotAcc_correlation.png"
    populationPlotFilename = "results/populationAcc_correlation.png"
    contactsPlotFilename = "results/contactsplotAcc_correlation.png"
    titlemetric = "Metrics Accumulative"
    titlepopulation = "Population Accumulative"
    titlecontacts = "Number of contacts Accumulative"

    plotClusteringData(pklObjectFilename, resname, titlemetric, titlepopulation,
                       titlecontacts, metricPlotFilename,
                       populationPlotFilename, contactsPlotFilename)

    plt.show()
