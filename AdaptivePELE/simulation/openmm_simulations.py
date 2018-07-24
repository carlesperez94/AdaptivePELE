"""
Helper functions to run with OpenMM, these  function could be methods of the
MDSimulation class however because of limitations imposed by the
multiprocessing they need to be functions
"""
from __future__ import absolute_import, division, print_function
import os
import sys
import time
import simtk.openmm as mm
import simtk.openmm.app as app
import simtk.unit as unit
from AdaptivePELE.constants import constants
try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError


class CustomStateDataReporter(app.StateDataReporter):
    """
    New version of the StateDataReporter class that allows to append the md information to the last trajectory file
    It has two new parameters: (append: bool, and initialStep: int). The first controls if the header has to be written
    again and the second is the last step that was successfully done in the previous run.
    """
    # Added two new parameters append and intialsteps to properly handle the report file when the simulation is restarted
    def __init__(self, file, reportInterval, step=False, time=False, potentialEnergy=False, kineticEnergy=False, totalEnergy=False, temperature=False, volume=False, density=False,
                 progress=False, remainingTime=False, speed=False, elapsedTime=False, separator=',', systemMass=None, totalSteps=None, append=False, initialStep=0):

        # This new class doesn't properly support progress information. Because to do the restart it assumes that
        # the first column has the step information, which is True as long as the progress value is False.

        progress = False
        app.StateDataReporter.__init__(self, file, reportInterval, step, time, potentialEnergy, kineticEnergy, totalEnergy, temperature, volume, density,
                 progress, remainingTime, speed, elapsedTime, separator, systemMass, totalSteps)
        self._append = append
        self.initialStep = initialStep

    def report(self, simulation, state):
        """Generate a report.

        Parameters
        ----------
        simulation : Simulation
            The Simulation to generate a report for
        state : State
            The current state of the simulation
        """
        if not self._hasInitialized:
            self._initializeConstants(simulation)
            headers = self._constructHeaders()
            # Extra line added to avoid printing the header again when the simulation is restarted
            if not self._append:
                print('#"%s"' % ('"' + self._separator + '"').join(headers), file=self._out)
            try:
                self._out.flush()
            except AttributeError:
                pass
            self._initialClockTime = time.time()
            self._initialSimulationTime = state.getTime()
            self._initialSteps = simulation.currentStep
            self._hasInitialized = True

        # Check for errors.
        self._checkForErrors(simulation, state)

        # Query for the values
        values = self._constructReportValues(simulation, state)

        # Write the values.
        print(self._separator.join(str(v) for v in values), file=self._out)
        try:
            self._out.flush()
        except AttributeError:
            pass

    def _constructReportValues(self, simulation, state):
        # Modifies the first value which is the step number information
        values = super(CustomStateDataReporter, self)._constructReportValues(simulation, state)
        values[0] = values[0] + self.initialStep
        return values




def runEquilibration(equilibrationFiles, outputPDB, parameters, worker):
    """
        Function that runs the whole equilibration process and returns the final pdb

        :param equilibrationFiles: tuple with the topology (prmtop) in the first position and the coordinates
        in the second (inpcrd)
        :type equilibrationFiles: tuple
        :param outputPDB: string with the pdb to save
        :type outputPDB: str
        :param parameters: Object with the parameters for the simulation
        :type parameters: :py:class:`/simulationrunner/SimulationParameters` -- SimulationParameters object
        :param worker: Number of the subprocess
        :type worker: int

        :returns: str -- a string with the outputPDB
    """
    prmtop, inpcrd = equilibrationFiles
    prmtop = app.AmberPrmtopFile(prmtop)
    inpcrd = app.AmberInpcrdFile(inpcrd)
    PLATFORM = mm.Platform_getPlatformByName(str(parameters.runningPlatform))
    if worker == 0:
        print("Running %d steps of minimization" % parameters.minimizationIterations)
    simulation = minimization(prmtop, inpcrd, PLATFORM, 5, parameters)
    positions = simulation.context.getState(getPositions=True).getPositions()
    velocities = simulation.context.getState(getVelocities=True).getVelocities()
    if worker == 0:
        print("Running %d steps of NVT equilibration" % parameters.equilibrationLength)
    simulation = NVTequilibration(prmtop, positions, PLATFORM, parameters.equilibrationLength, 5, parameters, velocities=velocities)
    positions = simulation.context.getState(getPositions=True).getPositions()
    velocities = simulation.context.getState(getVelocities=True).getVelocities()
    if worker == 0:
        print("Running %d steps of NPT equilibration" % parameters.equilibrationLength)
    simulation = NPTequilibration(prmtop, positions, PLATFORM, parameters.equilibrationLength, 0.5, parameters, velocities=velocities)
    with open(outputPDB, 'w') as fw:
        app.PDBFile.writeFile(simulation.topology, simulation.context.getState(getPositions=True).getPositions(), fw)
    return outputPDB


def minimization(prmtop, inpcrd, PLATFORM, constraints, parameters):
    """
    Function that runs a minimization of the system
    it uses the VerletIntegrator and applys to the heavy atoms of the
    protein and ligand.

    :param prmtop: OpenMM Topology object
    :param inpcrd: OpenMM Positions object
    :param PLATFORM: platform in which the minimization will run
    :type PLATFORM: str
    :param constraints: strength of the constrain (units: Kcal/mol)
    :type constraints: int
    :param parameters: Object with the parameters for the simulation
    :type parameters: :py:class:`/simulationrunner/SimulationParameters` -- SimulationParameters object

    :return: The minimized OpenMM simulation object
    """
    # Thermostat
    system = prmtop.createSystem(nonbondedMethod=app.PME,
                                 nonbondedCutoff=parameters.nonBondedCutoff * unit.angstroms, constraints=app.HBonds)
    # system.addForce(mm.AndersenThermostat(parameters.Temperature * unit.kelvin, 1 / unit.picosecond))
    integrator = mm.VerletIntegrator(2 * unit.femtoseconds)
    if constraints:
        # Add positional restraints to protein backbone
        force = mm.CustomExternalForce(str("k*((x-x0)^2+(y-y0)^2+(z-z0)^2)"))
        force.addGlobalParameter(str("k"), constraints * unit.kilocalories_per_mole / unit.angstroms ** 2)
        force.addPerParticleParameter(str("x0"))
        force.addPerParticleParameter(str("y0"))
        force.addPerParticleParameter(str("z0"))
        for j, atom in enumerate(prmtop.topology.atoms()):
            if (atom.name in ('CA', 'C', 'N', 'O') and atom.residue.name != "HOH") or (
                    atom.residue.name == parameters.ligandName and atom.element.symbol != "H"):
                force.addParticle(j, inpcrd.positions[j].value_in_unit(unit.nanometers))
        system.addForce(force)

    simulation = app.Simulation(prmtop.topology, system, integrator, PLATFORM)
    if inpcrd.boxVectors is not None:
        simulation.context.setPeriodicBoxVectors(*inpcrd.boxVectors)
    simulation.context.setPositions(inpcrd.positions)
    simulation.minimizeEnergy(maxIterations=parameters.minimizationIterations)
    return simulation


def NVTequilibration(topology, positions, PLATFORM, simulation_steps, constraints, parameters, velocities=None):
    """
    Function that runs an equilibration at constant volume conditions.
    It uses the AndersenThermostat, the VerletIntegrator and
    applys constrains to the heavy atoms of the protein and ligands

    :param topology: OpenMM Topology object
    :param positions: OpenMM Positions object
    :param PLATFORM: platform in which the minimization will run
    :type PLATFORM: str
    :param simulation_steps: number of steps to run
    :type simulation_steps: int
    :param constraints: strength of the constrain (units: Kcal/mol)
    :type constraints: int
    :param parameters: Object with the parameters for the simulation
    :type parameters: :py:class:`/simulationrunner/SimulationParameters` -- SimulationParameters object
    :param velocities: OpenMM object with the velocities of the system. Optional, if velocities are not given,
    random velocities acording to the temperature will be used.

    :return: The equilibrated OpenMM simulation object
    """
    system = topology.createSystem(nonbondedMethod=app.PME,
                                   nonbondedCutoff=parameters.nonBondedCutoff * unit.angstroms,
                                   constraints=app.HBonds)
    system.addForce(mm.AndersenThermostat(parameters.Temperature * unit.kelvin, 1 / unit.picosecond))
    integrator = mm.VerletIntegrator(2 * unit.femtoseconds)
    if constraints:
        force = mm.CustomExternalForce(str("k*((x-x0)^2+(y-y0)^2+(z-z0)^2)"))
        force.addGlobalParameter(str("k"), constraints * unit.kilocalories_per_mole / unit.angstroms ** 2)
        force.addPerParticleParameter(str("x0"))
        force.addPerParticleParameter(str("y0"))
        force.addPerParticleParameter(str("z0"))
        for j, atom in enumerate(topology.topology.atoms()):
            if (atom.name in ('CA', 'C', 'N', 'O') and atom.residue.name != "HOH") or (atom.residue.name == parameters.ligandName and atom.element.symbol != "H"):
                force.addParticle(j, positions[j].value_in_unit(unit.nanometers))
        system.addForce(force)
    simulation = app.Simulation(topology.topology, system, integrator, PLATFORM)
    simulation.context.setPositions(positions)
    if velocities:
        simulation.context.setVelocities(velocities)
    else:
        simulation.context.setVelocitiesToTemperature(parameters.Temperature * unit.kelvin, 1)
    simulation.step(simulation_steps)
    return simulation


def NPTequilibration(topology, positions, PLATFORM, simulation_steps, constraints, parameters, velocities=None):
    """
    Function that runs an equilibration at constant pressure conditions.
    It uses the AndersenThermostat, the VerletIntegrator, the MonteCarlo Barostat and
    apply's constrains to the backbone of the protein and to the heavy atoms of the ligand

    :param topology: OpenMM Topology object
    :param positions: OpenMM Positions object
    :param PLATFORM: platform in which the minimization will run
    :type PLATFORM: str
    :param simulation_steps: number of steps to run
    :type simulation_steps: int
    :param constraints: strength of the constrain (units: Kcal/mol)
    :type constraints: int
    :param parameters: Object with the parameters for the simulation
    :type parameters: :py:class:`/simulationrunner/SimulationParameters` -- SimulationParameters object
    :param velocities: OpenMM object with the velocities of the system. Optional, if velocities are not given,
    random velocities acording to the temperature will be used.

    :return: The equilibrated OpenMM simulation object
    """
    system = topology.createSystem(nonbondedMethod=app.PME,
                                   nonbondedCutoff=parameters.nonBondedCutoff * unit.angstroms,
                                   constraints=app.HBonds)
    system.addForce(mm.AndersenThermostat(parameters.Temperature * unit.kelvin, 1 / unit.picosecond))
    integrator = mm.VerletIntegrator(2 * unit.femtoseconds)
    system.addForce(mm.MonteCarloBarostat(1 * unit.bar, parameters.Temperature * unit.kelvin))
    if constraints:
        force = mm.CustomExternalForce(str("k*((x-x0)^2+(y-y0)^2+(z-z0)^2)"))
        force.addGlobalParameter(str("k"), constraints * unit.kilocalories_per_mole / unit.angstroms ** 2)
        force.addPerParticleParameter(str("x0"))
        force.addPerParticleParameter(str("y0"))
        force.addPerParticleParameter(str("z0"))
        for j, atom in enumerate(topology.topology.atoms()):
            if atom.name == 'CA' or (atom.residue.name == parameters.ligandName and atom.element.symbol != "H"):
                force.addParticle(j, positions[j].value_in_unit(unit.nanometers))
        system.addForce(force)
    simulation = app.Simulation(topology.topology, system, integrator, PLATFORM)
    simulation.context.setPositions(positions)
    if velocities:
        simulation.context.setVelocities(velocities)
    else:
        simulation.context.setVelocitiesToTemperature(parameters.Temperature * unit.kelvin, 1)
    simulation.step(simulation_steps)
    return simulation


def runProductionSimulation(equilibrationFiles, workerNumber, outputDir, seed, parameters, reportFileName, checkpoint, ligandName, restart=False):
    """
    Functions that runs the production run at NVT conditions.
    Ff a boxcenter is defined in the parameters section, Flat-bottom harmonic restrains will be applied to the ligand

    :param equilibrationFiles: Tuple with the paths for the Amber topology file (prmtop) and the pdb for the system
    :type equilibrationFiles: Tuple
    :param workerNumber: Number of the subprocess
    :type workerNumber: int
    :param outputDir: path to the directory where the output will be written
    :type outputDir: str
    :param seed: Seed to use to generate the random numbers
    :type seed: int
    :param parameters: Object with the parameters for the simulation
    :type parameters: :py:class:`/simulationrunner/SimulationParameters` -- SimulationParameters object
    :param reportFileName: Name for the file where the energy report will be written
    :type reportFileName: str
    :param checkpoint: Path to the checkpoint from where the production run will be restarted (Optional)
    :type checkpoint: str
    :param ligandName: Code Name for the ligand
    :type ligandName: str
    :param restart: Whether the simulation run has to be restarted or not
    :type restart: bool

    """
    prmtop, pdb = equilibrationFiles
    prmtop = app.AmberPrmtopFile(prmtop)
    DCDrepoter = os.path.join(outputDir, constants.AmberTemplates.trajectoryTemplate % workerNumber)
    stateReporter = os.path.join(outputDir, "%s_%s" % (reportFileName, workerNumber))
    checkpointReporter = os.path.join(outputDir, constants.AmberTemplates.CheckPointReporterTemplate % workerNumber)
    lastStep = getLastStep(stateReporter)
    simulation_length = parameters.productionLength - lastStep
    # if the string is unicode the PDBReaders fails to read the file (this is
    # probably due to the fact that openmm was built with python2 in my
    # computer, will need to test thoroughly with python3)
    pdb = app.PDBFile(str(pdb))
    PLATFORM = mm.Platform_getPlatformByName(str(parameters.runningPlatform))
    system = prmtop.createSystem(nonbondedMethod=app.PME,
                                 nonbondedCutoff=parameters.nonBondedCutoff * unit.angstroms,
                                 constraints=app.HBonds)
    system.addForce(mm.AndersenThermostat(parameters.Temperature * unit.kelvin, 1 / unit.picosecond))
    integrator = mm.VerletIntegrator(2 * unit.femtoseconds)
    if parameters.boxCenter:
        # Harmonic flat-bottom restrain for the ligand
        force = mm.CustomExternalForce('step(r-r0) * (k/2) * (r-r0)^2; r=sqrt((x-b0)^2+(y-b1)^2+(z-b2)^2)')
        force.addGlobalParameter("k", 5.0 * unit.kilocalories_per_mole / unit.angstroms ** 2)
        force.addGlobalParameter("r0", parameters.boxRadius)
        force.addGlobalParameter("b0", parameters.boxCenter[0])
        force.addGlobalParameter("b1", parameters.boxCenter[1])
        force.addGlobalParameter("b2", parameters.boxCenter[2])
        for j, atom in enumerate(prmtop.topology.atoms()):
            if atom.residue.name == ligandName:
                force.addParticle(j, [])
        system.addForce(force)
    simulation = app.Simulation(prmtop.topology, system, integrator, PLATFORM)
    simulation.context.setPositions(pdb.positions)

    if restart:
        with open(str(checkpoint), 'rb') as check:
            simulation.context.loadCheckpoint(check.read())
            stateData = open(str(stateReporter), "a")
    else:
        simulation.context.setVelocitiesToTemperature(parameters.Temperature * unit.kelvin, seed)
        stateData = open(str(stateReporter), "w")

    simulation.reporters.append(app.DCDReporter(str(DCDrepoter), parameters.reporterFreq, append=restart, enforcePeriodicBox=True))
    simulation.reporters.append(app.CheckpointReporter(str(checkpointReporter), parameters.reporterFreq))
    simulation.reporters.append(CustomStateDataReporter(stateData, parameters.reporterFreq, step=True,
                                                      potentialEnergy=True, temperature=True, time=True,
                                                      volume=True, remainingTime=True, speed=True,
                                                      totalSteps=parameters.productionLength, separator="\t",
                                                        append=restart, initialStep=lastStep))
    if workerNumber == 1:
        frequency = min(10 * parameters.reporterFreq, parameters.productionLength)
        simulation.reporters.append(app.StateDataReporter(sys.stdout, frequency, step=True))
    simulation.step(simulation_length)
    stateData.close()


def getLastStep(reportfile):
    """
    Function that given a MD report file extracts the last step that was properly done

    :param reportfile: reportfile with the previous md simulation
    :type reportfile: str
    :return: The number of the last step that was successfully done
    """
    try:
        with open(reportfile, "r") as inp:
            report = inp.read()
        last_step = report.split("\n")[-2].split("\t")[0]
    except FileNotFoundError:
        last_step = 0
    return int(last_step)