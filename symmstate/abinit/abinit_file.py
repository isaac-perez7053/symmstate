from . import AbinitUnitCell
import numpy as np
import os
import re
import subprocess
from symmstate.slurm_file import SlurmFile
import copy


class AbinitFile(AbinitUnitCell, SlurmFile):
    """
    Class dedicated to writing and executing Abinit files
    """

    def __init__(
        self,
        abi_file=None,
        batch_script_header_file=None,
        convergence_file=None,
        smodes_input=None,
        target_irrep=None,
        symmetry_informed_basis=False,
    ):

        AbinitUnitCell.__init__(
            self,
            abi_file=abi_file,
            convergence_file=convergence_file,
            smodes_input=smodes_input,
            target_irrep=target_irrep,
            symmetry_informed_basis=symmetry_informed_basis,
        )

        if abi_file is not None:
            print(f"Name of abinit file: {abi_file}")
            self.file_name = self.abi_file.replace(".abi", "")

        SlurmFile.__init__(self, batch_script_header_file)


        

    def write_custom_abifile(self, output_file, content, coords_are_cartesian=False):
        """
        Writes a custom Abinit .abi file using user-defined or default parameters.

        Args:
            output_file (str): Path where the new Abinit file will be saved.
            header_file (str): Header content or path to a header file.
            toldfe (bool): Flag indicating whether to append toldfe parameter. Defaults to True.
        """
        # Determine if the header_file is actual content or a path to a file
        if "\n" in content or not os.path.exists(content):
            # If it's likely content due to newline characters or non-existent path
            header_content = content
        else:
            # It's a valid file path; read the content from the file
            with open(content, "r") as hf:
                header_content = hf.read()

        # Get the unique file name if the name conflicts with other files
        output_file = AbinitFile._get_unique_filename(output_file)

        # Write all content to the output file
        with open(f"{output_file}.abi", "w") as outf:
            outf.write(header_content)

            # Append unit cell details
            outf.write("\n#--------------------------")
            outf.write("\n# Definition of unit cell")
            outf.write("\n#--------------------------\n")
            outf.write("acell 1.0 1.0 1.0\n")
            # Currently commented out to fix out the disparity between symmstate and acell
            # outf.write(f"acell {' '.join(map(str, self.acell))}\n") 
            outf.write("rprim\n")
            for coord in self.rprim:
                outf.write(f"  {'  '.join(map(str, coord))}\n")



            if coords_are_cartesian:
                outf.write("xcart\n")
                coordinates = self.grab_cartesian_coordinates()
                # Debug print: Inspect the coordinates before writing
                print("Coordinates to be written:", coordinates)
                for coord in coordinates:
                    # Convert each numpy array to a flat list
                    outf.write(f"  {'  '.join(map(str, coord))}\n")
            else:
                outf.write("xred\n")
                coordinates = self.grab_reduced_coordinates()
                for coord in coordinates:
                    # Convert each numpy array to a flat list
                    outf.write(f"  {'  '.join(map(str, coord))}\n")

            outf.write("\n#--------------------------")
            outf.write("\n# Definition of atoms")
            outf.write("\n#--------------------------\n")
            outf.write(f"natom {self.natom} \n")
            outf.write(f"ntypat {self.ntypat} \n")
            outf.write(f"znucl {' '.join(map(str, self.znucl))}\n")
            outf.write(f"typat {' '.join(map(str, self.typat))}\n")

            if self.convergence_file is None:
                outf.write("\n#----------------------------------------")
                outf.write("\n# Definition of the planewave basis set")
                outf.write("\n#----------------------------------------\n")
                outf.write(f"ecut {self.ecut} \n")
                if self.ecutsm is not None:
                    outf.write(f"ecutsm {self.ecutsm} \n")

                outf.write("\n#--------------------------")
                outf.write("\n# Definition of the k-point grid")
                outf.write("\n#--------------------------\n")
                outf.write(f"nshiftk {self.nshiftk} \n")
                outf.write("kptrlatt\n")
                if self.kptrlatt is not None:
                    for i in self.kptrlatt:
                        outf.write(f"  {' '.join(map(str, i))}\n")
                outf.write(f"shiftk {' '.join(map(str, self.shiftk))} \n")
                outf.write(f"nband {self.nband} \n")
                outf.write("\n#--------------------------")
                outf.write("\n# Definition of the SCF Procedure")
                outf.write("\n#--------------------------\n")
                outf.write(f"nstep {self.nstep} \n")
                outf.write(f"diemac {self.diemac} \n")
                outf.write(f"ixc {self.ixc} \n")

                outf.write(f"{self.conv_criteria[0]} {str(self.conv_criteria[1])} \n")

                # Calculate the path to the pp directory
                package_path_rel = SlurmFile.upload_files_to_package(
                    dest_folder_name='pseudopotentials'
                )

                # Check to make sure package was found and print relative path
                if not package_path_rel:
                    raise FileNotFoundError(
                        "Package path was not found! This is likely an issue if it wasn't installed using pip"
                    )
                else:
                    outf.write(
                        f'\npp_dirpath "{package_path_rel}" \n'
                    )

                concatenated_pseudos = " ".join(self.pseudopotentials)

                outf.write(f'pseudos "{concatenated_pseudos}" \n')
                print(f"The Abinit file {output_file} was created successfully! \n")

            else:
                with open(self.convergence_file, "r") as cf:
                    convergence_content = cf.read()
                outf.write(convergence_content)

    def write_ground_workfunction_file(self, output_path):
        """
        Creates an Abinit input file to calculate the ground work function of the unit cell.

        Args:
            output_path (str): Directory to save the generated Abinit input file.
        """

        # TODO: I don't want the tolwfr to be hardcoded. I think an easy fix around is give users the ability to create their own file.
        content = """
  ndtset 2

#Set 1 : Ground State Self-Consistent Calculation
#************************************************

  kptopt1 1
  tolvrs 1.0d-18

#Set 2 : Calculation of ddk wavefunctions
#************************************************
  kptopt2 2             # DDK can use only time reversal symmetry
  getwfk2 1             # require ground state wavefunctions from previous run
  rfelfd2 2             # activate DDK perturbation
  iscf2   -3            # this is a non-self-consistent calculation
  tolwfr2 1.0D-18       # tight convergence on wavefunction residuals
"""

        self.write_custom_abifile(output_file=output_path, content=content)

    def write_phonon_dispersion_file(self, output_path):
        """
        Generates an Abinit input file for calculating the phonon dispersion curve of the unit cell.

        Args:
            output_path (str): Directory to save the generated Abinit input file.
        """
        # TODO: the ngqpt is currently hardcoded and needs to be manually calculated.

        content = """

  ndtset 6

#Definition of q-point grid
#**************************

  nqpt 1     # One qpt for each dataset
  qptopt 1
  ngqpt 4 4 4
  nshiftq 1
  shiftq 0.0 0.0 0.0

iqpt: 5 iqpt+ 1   #automatically iterate through the q pts

#Set 1 : iqpt 1 is the gamma point, so Q=0 phonons and electric field pert.
#**************************************************************************

  getddk1   98         # d/dk wave functions
  kptopt1   2          # Use of time-reversal symmetry
  rfelfd1   3          # Electric-field perturbation response
                       # (in addition to default phonon)

#Sets 2-20 : Finite-wave-vector phonon calculations (defaults for all datasets)
#******************************************************************************

   getwfk  99           # Use GS wave functions
   kptopt  3
   rfphon  1          # Do phonon response
   tolvrs  1.0d-15    # Converge on potential residual

#******
#Flags*
#******

   prtwf 1
   prtden 1
   prtpot 1
   prteig 0
"""
        self.write_custom_abifile(output_file=output_path, content=content)

    # ----------------------
    # File Execution Methods
    # ----------------------

    def run_abinit(
        self,
        input_file="abinit",
        batch_name="abinit_job",
        batch_script_header_file=None,
        host_spec="mpirun -hosts=localhost -np 30",
        delete_batch_script=True,
        log="log",
    ):
        """
        Executes the Abinit program using a generated input file and specified settings.

        Args:
            input_file (str): The name of the Abinit input file to be executed. Defaults to 'abinit'.
            batch_name (str): The name of the batch script to be generated. Defaults to 'abinit_job'.
            batch_script_header_file (str): File path for the batch script header.
            host_spec (str): Command specifying options for parallel execution environment. Defaults as shown.
            delete_batch_script (bool): Whether to delete the batch script after execution. Default is True.
            log (str): Filename for logging output. Defaults to "log".
        """

        # Compile the content to be written in the file
        content = f"""{input_file}.abi
{input_file}.abo
{input_file}o
{input_file}_gen_output
{input_file}_temp
    """
        if batch_script_header_file is not None:
            # Create a non-temporary file in the current directory
            file_path = f"{input_file}_abinit_input_data.txt"

            # Check to make sure the file name does not conflict
            file_path = AbinitFile._get_unique_filename(file_path)

            with open(file_path, "w") as file:
                file.write(content)
            try:
                batch_name = AbinitFile._get_unique_filename(f"{batch_name}.sh")
                batch_name = os.path.basename(batch_name)

                # Use the regular file's path in your operations
                script_created = self.write_batch_script(
                    input_file=file_path,
                    batch_name=batch_name,
                    host_spec=host_spec,
                    log=log,
                )
                print(f"Was the batch script successfully created: {script_created} \n")

                # Submit the job using subprocess to capture output
                result = subprocess.run(
                    ["sbatch", batch_name], capture_output=True, text=True
                )

                if result.returncode == 0:
                    print("Batch job submitted using 'sbatch'.")
                    try:
                        job_number = int(result.stdout.strip().split()[-1])
                        self.running_jobs.append(job_number)
                        print(f"Job number {job_number} added to running jobs.")
                    except (ValueError, IndexError) as e:
                        print(f"Failed to parse job number: {e}")
                else:
                    print("Failed to submit batch job:", result.stderr)

            finally:
                if delete_batch_script:
                    batch_script_path = f"{batch_name}.sh"
                    if os.path.exists(batch_script_path):
                        os.remove(batch_script_path)
                        print(f"Batch script '{batch_script_path}' has been removed.")

        else:
            command = f"{host_spec} abinit < {input_file} > {log}"
            os.system(command)
            print(f"Abinit executed directly. Output written to '{log}'.")

    def run_piezo_calculation(self, host_spec="mpirun -hosts=localhost -np 30"):
        """
        Runs a piezoelectricity calculation for the unit cell using default or provided host specifications.

        Args:
            host_spec (str): Specification for parallel execution environment. Defaults as shown.
        """
        content = """ndtset 4

# Set 1: Ground State Self-Consistency
#*************************************

getwfk1 0
kptopt1 1
tolvrs1 1.0d-18

# Set 2: Reponse function calculation of d/dk wave function
#**********************************************************

iscf2 -3
rfelfd2 2
tolwfr2 1.0d-20

# Set 3: Response function calculation of d2/dkdk wavefunction
#*************************************************************

getddk3 2
iscf3 -3
rf2_dkdk3 3
tolwfr3 1.0d-16
rf2_pert1_dir3 1 1 1
rf2_pert2_dir3 1 1 1

# Set 4: Response function calculation to q=0 phonons, electric field and strain
#*******************************************************************************
getddk4 2
rfelfd4 3
rfphon4 1
rfstrs4 3
rfstrs_ref4 1
tolvrs4 1.0d-8

getwfk 1
useylm 1  # Use of spherical harmonics
kptopt 2  # Takes into account time-reversal symmetry. 
"""
        # Get the current working directory
        working_directory = os.getcwd()

        # Construct the full paths for the output and batch files
        output_file = os.path.join(working_directory, f"{self.file_name}_piezo")
        batch_name = os.path.join(working_directory, f"{self.file_name}_bscript")

        # Use these paths in your methods
        self.write_custom_abifile(
            output_file=output_file, content=content, coords_are_cartesian=False
        )
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            batch_script_header_file=self.batch_header,
        )

    def run_flexo_calculation(self, host_spec="mpirun -hosts=localhost -np 30"):
        """
        Runs a flexoelectricity calculation for the unit cell using default or provided host specifications.

        Args:
            host_spec (str): Specification for parallel execution environment. Defaults as shown.
        """
        content = """ndtset 5

# Set 1: Ground State Self-Consistency
#*************************************

getwfk1 0
kptopt1 1
tolvrs1 1.0d-18

# Set 2: Reponse function calculation of d/dk wave function
#**********************************************************

iscf2 -3
rfelfd2 2
tolwfr2 1.0d-20

# Set 3: Response function calculation of d2/dkdk wavefunction
#*************************************************************

getddk3 2
iscf3 -3
rf2_dkdk3 3
tolwfr3 1.0d-16
rf2_pert1_dir3 1 1 1
rf2_pert2_dir3 1 1 1

# Set 4: Response function calculation to q=0 phonons, electric field and strain
#*******************************************************************************
getddk4 2
rfelfd4 3
rfphon4 1
rfstrs4 3
rfstrs_ref4 1
tolvrs4 1.0d-8
prepalw4 1

# Set 5: Long-wave Calculations
#******************************

optdriver5 10
get1wf5 4
get1den5 4
getddk5 2
getdkdk5 3
lw_flexo5 1


getwfk 1
useylm 1  # Use of spherical harmonics
kptopt 2  # Takes into account time-reversal symmetry. 
"""
        # Get the current working directory
        working_directory = os.getcwd()

        # Construct the full paths for the output and batch files
        output_file = os.path.join(working_directory, f"{self.file_name}_flexo")
        batch_name = os.path.join(working_directory, f"{self.file_name}_bscript")

        # Use these paths in your methods
        self.write_custom_abifile(
            output_file=output_file, content=content, coords_are_cartesian=False
        )
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            batch_script_header_file=self.batch_header,
        )

    def run_energy_calculation(self, host_spec="mpirun -hosts=localhost -np 20"):
        """
        Runs an energy calculation for the unit cell using default or provided host specifications.

        Args:
            host_spec (str): Specification for parallel execution environment. Defaults as shown.
        """
        content = """ndtset 1

# Ground State Self-Consistency
#*******************************

getwfk1 0
kptopt1 1

# turn off various file outputs
prtpot 0
prteig 0


getwfk 1
useylm 1  # Use of spherical harmonics
kptopt 2  # Takes into account time-reversal symmetry.

"""
        # Get the current working directory
        working_directory = os.getcwd()

        # Construct the full paths for the output and batch files
        output_file = os.path.join(working_directory, f"{self.file_name}_energy")
        batch_name = os.path.join(working_directory, f"{self.file_name}_bscript")

        # Use these paths in your methods
        self.write_custom_abifile(
            output_file=output_file, content=content, coords_are_cartesian=True
        )
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            batch_script_header_file=self.batch_header,
            log=f"{output_file}.log"
        )

    # Implement this function like I did with anaddb
    def run_anaddb_file(self, ddb_file, content="" ,flexo=False, peizo=False):
        if flexo:
            content_f = """
! anaddb calculation of flexoelectric tensor

flexoflag 1
"""
            files_content = f"""{self.file_name}_flexo_anaddb.abi
{self.file_name}_flexo_output
{ddb_file}
dummy1
dummy2
dummy3
dummy4
"""
            # Write all content to the output file
            with open(f"{self.file_name}_flexo_anaddb.abi", "w") as outf:
                outf.write(content_f)
            
            with open(f"{self.file_name}_flexo_anaddb.files", "w") as outff:
                outff.write(files_content)

            # Execute anaddb directly through the terminal
            command = f"anaddb < {self.file_name}_flexo_anaddb.files > {self.file_name}_flexo_anaddb.log"

            try:
                # Run the command
                subprocess.run(command, shell=True, check=True)
                print(f"Command executed successfully: {command}")
            except subprocess.CalledProcessError as e:
                print(f"An error occurred while executing the command: {e}")
            
            # Return the name of the output file 
            return f"{self.file_name}_flexo_output"

        elif peizo:
            content_p = """
! Input file for the anaddb code

elaflag 3  ! flag for the elastic constant
piezoflag 3 !the flag for the piezoelectric constant
instrflag 1 ! the flag for the internal strain tensor
"""
            files_content = f"""
{self.file_name}_piezo_anaddb.abi
{self.file_name}_piezo_output
{ddb_file}
dummy1
dummy2
dummy3
"""
            # Write all content to the output file
            with open(f"{self.file_name}_piezo_anaddb.abi", "w") as outf:
                outf.write(content_p)
            
            with open(f"{self.file_name}_piezo_anaddb.files", "w") as outff:
                outff.write(files_content)

            # Execute anaddb directly through the terminal
            command = f"anaddb < {self.file_name}_piezo_anaddb.files > {self.file_name}_piezo_anaddb.log"

            try:
                # Run the command
                subprocess.run(command, shell=True, check=True)
                print(f"Command executed successfully: {command}")
            except subprocess.CalledProcessError as e:
                print(f"An error occurred while executing the command: {e}")
            
            # Return the name of the output file 
            return f"{self.file_name}_piezo_output"

# TODO: Below is what the anaddb function should be. The above can be implemented into Perturbations.py
        else: 
            # Write all content to the output file
            with open(f"{self.file_name}_anaddb.abi", "w") as outf:
                outf.write(content)

            # Execute anaddb directly through the terminal
            command = f"anaddb < {self.file_name}_anaddb.files > {self.file_name}_anaddb.log"

            try:
                # Run the command
                subprocess.run(command, shell=True, check=True)
                print(f"Command executed successfully: {command}")
            except subprocess.CalledProcessError as e:
                print(f"An error occurred while executing the command: {e}")
            
            
        



    def run_mrgddb_file(self, content):
        # Write all content to the output file
        with open(f"{self.file_name}_mrgddb.in", "w") as outf:
            outf.write(content)
        
        # Execute mrgddb directly through the terminal
        command = f"mrgddb < {self.file_name}_mrgddb.in"
        
        try:
            # Run the command and capture stdout and stderr
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Command executed successfully: {command}")
            print(f"Output: {result.stdout.decode()}")  # Decode and print output
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while executing the command: {e}")
            print(f"Error output: {e.stderr.decode()}")  # Print the error output if any




    # ---------------------------------
    # File Extraction methods
    # ---------------------------------

    def grab_energy(self, abo_file):
        """
        Retrieves and assigns the total energy from a specified Abinit output file (`abo_file`).

        Args:
            abo_file (str, optional): The path to the Abinit output file. Defaults to auto-generated name.

        Raises:
            FileNotFoundError: If the specified `abo_file` does not exist.
        """
        if abo_file is None:
            raise Exception("Please specify the abo file you are attempting to access")

        # Ensure total_energy_value is initialized
        total_energy_value = None

        try:
            with open(abo_file) as f:
                # Read all content as a single string
                abo_content = f.read()

            # Apply the regex pattern to the full content
            match = re.search(r"total_energy\s*:\s*(-?\d+\.\d+E?[+-]?\d*)", abo_content)

            if match:
                total_energy_value = match.group(1)
                self.energy = float(total_energy_value)
            else:
                print("Total energy not found.")
                

        except FileNotFoundError:
            print(f"The file {abo_file} was not found.")

    def grab_flexo_tensor(self, anaddb_file=None):
        """
        Retrieves the TOTAL flexoelectric tensor from the specified file.

        Args:
            anaddb_file (str, optional): The path to the Abinit output file. Defaults to a generated file name.

        Raises:
            FileNotFoundError: If the specified `anaddb_file` does not exist.
        """
        if anaddb_file is None:
            anaddb_file = f"file_name_energy.abo"

        # Initialize array to store the flexoelectric tensor
        flexo_tensor = None

        try:
            with open(anaddb_file) as f:
                # Read all content as a single string
                abo_content = f.read()

            # Extract TOTAL flexoelectric tensor
            flexo_match = re.search(
                r"TOTAL flexoelectric tensor \(units= nC/m\)\s*\n\s+xx\s+yy\s+zz\s+yz\s+xz\s+xy\n((?:.*\n){9})",
                abo_content,
            )
            
            if flexo_match:
                tensor_strings = flexo_match.group(1).strip().split("\n")
                flexo_tensor = np.array(
                    [list(map(float, line.split()[1:])) for line in tensor_strings]
                )

        except FileNotFoundError:
            print(f"The file {anaddb_file} was not found.")
        
        self.flexo_tensor = flexo_tensor

    def parse_tensor(self, tensor_str):
        """
        Parses a tensor string into a NumPy array.
        Assumes the tensor data is represented as lines of space-separated numbers.
        """
        lines = tensor_str.strip().splitlines()
        tensor_data = []

        for line in lines:
            # Split each line into parts and attempt to cast them to floats
            elements = line.split()
            if all(part.lstrip('-').replace('.', '', 1).isdigit() for part in elements):
                try:
                    numbers = [float(value) for value in elements]
                    tensor_data.append(numbers)
                except ValueError as e:
                    print(f"Could not convert line to numbers: {line}, Error: {e}")
                    raise

        return np.array(tensor_data)

    def grab_piezo_tensor(self, anaddb_file=None):
        """
        Retrieves the clamped and relaxed ion piezoelectric tensors.

        Args:
            abo_file (str, optional): The path to the Abinit output file. Defaults to auto-generated name.

        Raises:
            FileNotFoundError: If the specified `abo_file` does not exist.
        """
        if anaddb_file is None:
            anaddb_file = f"{self.file_name}_energy.abo"

        # Initialize arrays to store piezoelectric tensors
        piezo_tensor_clamped = None
        piezo_tensor_relaxed = None

        try:
            with open(anaddb_file) as f:
                # Read all content as a single string
                abo_content = f.read()

            # Extract clamped ion piezoelectric tensor
            clamped_match = re.search(
                r"Proper piezoelectric constants \(clamped ion\) \(unit:c/m\^2\)\s*\n((?:\s*-?\d+\.\d+\s+\n?)+)",
                abo_content,
            )
            if clamped_match:
                clamped_strings = clamped_match.group(1).strip().split("\n")
                piezo_tensor_clamped = np.array(
                    [list(map(float, line.split())) for line in clamped_strings]
                )

            # Extract relaxed ion piezoelectric tensor
            relaxed_match = re.search(
                r"Proper piezoelectric constants \(relaxed ion\) \(unit:c/m\^2\)\s*\n((?:\s*-?\d+\.\d+\s+\n?)+)",
                abo_content,
            )
            if relaxed_match:
                relaxed_strings = relaxed_match.group(1).strip().split("\n")
                piezo_tensor_relaxed = np.array(
                    [list(map(float, line.split())) for line in relaxed_strings]
                )

        except FileNotFoundError:
            print(f"The file {anaddb_file} was not found.")

        self.piezo_tensor_clamped = piezo_tensor_clamped
        self.piezo_tensor_relaxed = piezo_tensor_relaxed

    def clean_files(self, filename="filename.abi"):
        pass

    def copy_abinit_file(self):
        """
        Creates a deep copy of the current AbinitFile instance.

        Returns:
            AbinitFile: A new instance that is a deep copy of the current instance.
        """
        # Perform a deep copy to ensure all nested objects are also copied
        copied_file = copy.deepcopy(self)
        return copied_file
