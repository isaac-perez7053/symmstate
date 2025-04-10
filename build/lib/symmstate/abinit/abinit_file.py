from . import AbinitUnitCell
import os
import subprocess
import copy
from symmstate.pseudopotentials.pseudopotential_manager import PseudopotentialManager
from typing import Optional, List
from symmstate.slurm_file import SlurmFile
from pymatgen.core import Structure

class AbinitFile(AbinitUnitCell):
    """
    Class dedicated to writing and executing Abinit files.
    
    Revised functionality:
      - The user supplies a SlurmFile object (slurm_obj) which controls job submission,
        batch script creation, and holds running job IDs.
      - All messages are routed to the global logger.
      - Type hints and explicit type casting are used throughout.
    """

    def __init__(
        self,
        abi_file: Optional[str] = None,
        unit_cell: Optional[Structure] = None,
        slurm_obj: Optional[SlurmFile] = None,
        *,
        smodes_input: Optional[str] = None,
        target_irrep: Optional[str] = None,
    ) -> None:
        # Initialize AbinitUnitCell with supported parameters.
        AbinitUnitCell.__init__(
            self,
            abi_file=abi_file,
            unit_cell=unit_cell,
            smodes_input=smodes_input,
            target_irrep=target_irrep,
        )

        if abi_file is not None:
            self._logger.info(f"Name of abinit file: {abi_file}")
            self.file_name: str = str(abi_file).replace(".abi", "")
        else:
            self.file_name = "default_abinit_file"

        # Save it as self.slurm_obj. If none is supplied, log a warning.
        if slurm_obj is None:
            self._logger.info("No SlurmFile object supplied; job submission may not work as intended.")
            
        self.slurm_obj: Optional[SlurmFile] = slurm_obj

    @staticmethod
    def _get_unique_filename(file_name: str) -> str:
        """Generate a unique filename by appending a counter if the file exists."""
        base, ext = os.path.splitext(file_name)
        counter = 1
        unique_name = file_name
        while os.path.exists(unique_name):
            unique_name = f"{base}_{counter}{ext}"
            counter += 1
        return unique_name

    def write_custom_abifile(self, output_file: str, content: str, coords_are_cartesian: bool = False, pseudos: List = []) -> None:
        """
        Writes a custom Abinit .abi file using user-defined or default parameters.

        Args:
            output_file (str): Path where the new Abinit file will be saved.
            content (str): Header content or path to a header file.
            coords_are_cartesian (bool): Flag indicating the coordinate system.
        """
        # Determine whether 'content' is literal text or a file path.
        if "\n" in content or not os.path.exists(content):
            header_content: str = content
        else:
            with open(content, "r") as hf:
                header_content = hf.read()

        # Generate a unique filename.
        output_file = AbinitFile._get_unique_filename(output_file)

        with open(f"{output_file}.abi", "w") as outf:
            # Write the header content
            outf.write(header_content)
            outf.write("\n#--------------------------\n# Definition of unit cell\n#--------------------------\n")
            acell = self.vars.get("acell", self.structure.lattice.abc) 
            outf.write(f"acell {' '.join(map(str, acell))}\n")
            rprim = self.vars.get("rprim", self.structure.lattice.matrix.tolist()) 
            outf.write("rprim\n")

            for coord in rprim:
                outf.write(f"  {'  '.join(map(str, coord))}\n")

            if coords_are_cartesian:
                outf.write("xcart\n")
                coordinates = self.vars['xcart']
                self._logger.info(f"Coordinates to be written: {coordinates}")

                for coord in coordinates:
                    outf.write(f"  {'  '.join(map(str, coord))}\n")

            else:
                outf.write("xred\n")
                coordinates = self.vars['xred']
                for coord in coordinates:
                    outf.write(f"  {'  '.join(map(str, coord))}\n")

            outf.write("\n#--------------------------\n# Definition of atoms\n#--------------------------\n")
            outf.write(f"natom {self.vars['natom']} \n")
            outf.write(f"ntypat {self.vars['ntypat']} \n")
            outf.write(f"znucl {' '.join(map(str, self.vars['znucl']))}\n")
            outf.write(f"typat {' '.join(map(str, self.vars['typat']))}\n")

            outf.write("\n#----------------------------------------\n# Definition of the planewave basis set\n#----------------------------------------\n")
            outf.write(f"ecut {self.vars.get('ecut', 42)} \n")
            if self.vars['ecutsm'] is not None:
                outf.write(f"ecutsm {self.vars['ecutsm']} \n")

            outf.write("\n#--------------------------\n# Definition of the k-point grid\n#--------------------------\n")
            outf.write(f"nshiftk {self.vars.get('nshiftk', '1')} \n")
            outf.write("kptrlatt\n")
            if self.vars['kptrlatt'] is not None:
                for i in self.vars['kptrlatt']:
                    outf.write(f"  {' '.join(map(str, i))}\n")
            outf.write(f"shiftk {' '.join(map(str, self.vars.get('shiftk', '0.5 0.5 0.5')))} \n")
            outf.write(f"nband {self.vars['nband']} \n")

            outf.write("\n#--------------------------\n# Definition of the SCF Procedure\n#--------------------------\n")
            outf.write(f"nstep {self.vars.get('nstep', 9)} \n")
            outf.write(f"diemac {self.vars.get('diemac', '1000000.0')} \n")
            outf.write(f"ixc {self.vars['ixc']} \n")
            outf.write(f"{self.vars['conv_criteria']} {str(self.vars[self.vars['conv_criteria']])} \n")
            # Use pseudopotential information parsed into self.vars.
            pp_dir_path = PseudopotentialManager().folder_path
            outf.write(f'\npp_dirpath "{pp_dir_path}" \n')
            if len(pseudos) == 0:
                pseudos = self.vars.get("pseudos", [])
            concatenated_pseudos = ", ".join(pseudos).replace('"', '')
            outf.write(f'pseudos "{concatenated_pseudos}"\n')
            self._logger.info(f"The Abinit file {output_file} was created successfully!")


    def run_abinit(
        self,
        input_file: str = "abinit",
        batch_name: str = "abinit_job",
        host_spec: str = "mpirun -hosts=localhost -np 30",
        delete_batch_script: bool = True,
        log: str = "log",
    ) -> None:
        """
        Executes the Abinit program using a generated input file and specified settings.
        """
        content: str = f"""{input_file}.abi
{input_file}.abo
{input_file}o
{input_file}_gen_output
{input_file}_temp
        """
        # We now require a SlurmFile object (self.slurm_obj) to handle batch script operations.
        if self.slurm_obj is not None:
            file_path: str = f"{input_file}_abinit_input_data.txt"
            file_path = AbinitFile._get_unique_filename(file_path)
            with open(file_path, "w") as file:
                file.write(content)
            try:
                batch_name = AbinitFile._get_unique_filename(f"{batch_name}.sh")
                batch_name = os.path.basename(batch_name)
                # Use the provided SlurmFile object.
                script_created = self.slurm_obj.write_batch_script(
                    input_file=f"{input_file}.abi",
                    log_file=log,
                    batch_name=batch_name,
                )
                self._logger.info(f"Batch script created: {script_created}")
                result = subprocess.run(
                    ["sbatch", batch_name], capture_output=True, text=True
                )
                if result.returncode == 0:
                    self._logger.info("Batch job submitted using 'sbatch'.")
                    try:
                        job_number = int(result.stdout.strip().split()[-1])
                        self.slurm_obj.running_jobs.append(job_number)
                        self._logger.info(f"Job number {job_number} added to running jobs.")
                    except (ValueError, IndexError) as e:
                        self._logger.info(f"Failed to parse job number: {e}")
                else:
                    self._logger.error(f"Failed to submit batch job: {result.stderr}")
            finally:
                if delete_batch_script:
                    batch_script_path = f"{batch_name}.sh"
                    if os.path.exists(batch_script_path):
                        os.remove(batch_script_path)
                        self._logger.info(f"Batch script '{batch_script_path}' has been removed.")
        else:
            # If no SlurmFile object was provided, execute directly.
            command: str = f"{host_spec} abinit < {input_file} > {log}"
            os.system(command)
            self._logger.info(f"Abinit executed directly. Output written to '{log}'.")

    def run_piezo_calculation(self, host_spec: str = "mpirun -hosts=localhost -np 30") -> None:
        """
        Runs a piezoelectricity calculation for the unit cell.
        """
        content: str = """ndtset 2
chkprim 0

# Set 1 : Ground State Self-Consistent Calculation
#************************************************
  kptopt1 1
  tolvrs 1.0d-18

# Set 2 : Calculation of ddk wavefunctions
#************************************************
  kptopt2 2
  getwfk2 1
  rfelfd2 2
  iscf2   -3
  tolwfr2 1.0D-18
"""
        working_directory: str = os.getcwd()
        output_file: str = os.path.join(working_directory, f"{self.file_name}_piezo")
        batch_name: str = os.path.join(working_directory, f"{self.file_name}_bscript")
        self.write_custom_abifile(output_file=output_file, content=content, coords_are_cartesian=False)
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            log="log"
        )

    def run_flexo_calculation(self, host_spec: str = "mpirun -hosts=localhost -np 30") -> None:
        """
        Runs a flexoelectricity calculation for the unit cell.
        """
        content: str = """ndtset 5
chkprim 0

# Set 1: Ground State Self-Consistency
#*************************************
getwfk1 0
kptopt1 1
tolvrs1 1.0d-18

# Set 2: Response function calculation of d/dk wave function
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

getwfk 1
useylm 1
kptopt2 2
"""
        working_directory: str = os.getcwd()
        output_file: str = os.path.join(working_directory, f"{self.file_name}_flexo")
        batch_name: str = os.path.join(working_directory, f"{self.file_name}_bscript")
        self.write_custom_abifile(output_file=output_file, content=content, coords_are_cartesian=False)
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            log="log"
        )

    def run_energy_calculation(self, host_spec: str = "mpirun -hosts=localhost -np 20") -> None:
        """
        Runs an energy calculation for the unit cell.
        """
        content: str = """ndtset 1
chkprim 0

# Ground State Self-Consistency
#*******************************
getwfk1 0
kptopt1 1

# Turn off various file outputs
prtpot 0
prteig 0

getwfk 1
useylm 1
kptopt2 2
"""
        working_directory: str = os.getcwd()
        output_file: str = os.path.join(working_directory, f"{self.file_name}_energy")
        batch_name: str = os.path.join(working_directory, f"{self.file_name}_bscript")
        self.write_custom_abifile(output_file=output_file, content=content, coords_are_cartesian=True)
        self.run_abinit(
            input_file=output_file,
            batch_name=batch_name,
            host_spec=host_spec,
            log=f"{output_file}.log"
        )

    def run_anaddb_file(
        self,
        content: str = "",
        files_content: str = "",
        *, 
        ddb_file: str,
        flexo: bool = False,
        peizo: bool = False
    ) -> str:
        """
        Executes an anaddb calculation. Supports default manual mode and optional presets for flexoelectric or piezoelectric calculations.

        Args:
            ddb_file: Path to the DDB file.
            content: Content to write into the .abi file (used if neither flexo nor peizo are True).
            files_content: Content for the .files file (used if neither flexo nor peizo are True).
            flexo: If True, runs a flexoelectric preset calculation.
            peizo: If True, runs a piezoelectric preset calculation.

        Returns:
            str: Name of the output file produced.
        """
        if flexo:
            content = """
    ! anaddb calculation of flexoelectric tensor
    flexoflag 1
    """.strip()

            files_content = f"""{self.file_name}_flexo_anaddb.abi
    {self.file_name}_flexo_output
    {ddb_file}
    dummy1
    dummy2
    dummy3
    dummy4
    """.strip()

            abi_path = f"{self.file_name}_flexo_anaddb.abi"
            files_path = f"{self.file_name}_flexo_anaddb.files"
            log_path = f"{self.file_name}_flexo_anaddb.log"
            output_file = f"{self.file_name}_flexo_output"

        elif peizo:
            content = """
    ! Input file for the anaddb code
    elaflag 3
    piezoflag 3
    instrflag 1
    """.strip()

            files_content = f"""{self.file_name}_piezo_anaddb.abi
    {self.file_name}_piezo_output
    {ddb_file}
    dummy1
    dummy2
    dummy3
    """.strip()

            abi_path = f"{self.file_name}_piezo_anaddb.abi"
            files_path = f"{self.file_name}_piezo_anaddb.files"
            log_path = f"{self.file_name}_piezo_anaddb.log"
            output_file = f"{self.file_name}_piezo_output"

        else:
            if not content.strip() or not files_content.strip():
                raise ValueError("Must provide both `content` and `files_content` when not using flexo or peizo mode.")

            abi_path = f"{self.file_name}_anaddb.abi"
            files_path = f"{self.file_name}_anaddb.files"
            log_path = f"{self.file_name}_anaddb.log"
            output_file = f"{self.file_name}_anaddb_output"

        # Write files
        with open(abi_path, "w") as abi_file:
            abi_file.write(content)
        with open(files_path, "w") as files_file:
            files_file.write(files_content)

        # Run the anaddb command
        command = f"anaddb < {files_path} > {log_path}"
        try:
            subprocess.run(command, shell=True, check=True)
            self._logger.info(f"Command executed successfully: {command}")
        except subprocess.CalledProcessError as e:
            self._logger.error(f"An error occurred while executing the command: {e}")

        return output_file
    
    def copy_abinit_file(self):
        """
        Creates a deep copy of the current AbinitFile instance.

        Returns:
            AbinitFile: A new instance that is a deep copy of self.
        """
        return copy.deepcopy(self)


    def __repr__(self):

        lines = []
        lines.append("#--------------------------")
        lines.append("# Definition of unit cell")
        lines.append("#--------------------------")
        acell = self.vars.get("acell", self.structure.lattice.abc)
        lines.append(f"acell {' '.join(map(str, acell))}")
        rprim = self.vars.get("rprim", self.structure.lattice.matrix.tolist())
        lines.append("rprim")
        for coord in rprim:
            lines.append(f"  {'  '.join(map(str, coord))}")
        # Choose coordinate system: xcart if available; otherwise xred.
        if self.vars.get("xcart") is not None:
            lines.append("xcart")
            coordinates = self.vars['xcart']
            for coord in coordinates:
                lines.append(f"  {'  '.join(map(str, coord))}")
        else:
            lines.append("xred")
            coordinates = self.vars.get("xred", [])
            for coord in coordinates:
                lines.append(f"  {'  '.join(map(str, coord))}")
        lines.append("")
        lines.append("#--------------------------")
        lines.append("# Definition of atoms")
        lines.append("#--------------------------")
        lines.append(f"natom {self.vars.get('natom')}")
        lines.append(f"ntypat {self.vars.get('ntypat')}")
        lines.append(f"znucl {' '.join(map(str, self.vars.get('znucl', [])))}")
        lines.append(f"typat {' '.join(map(str, self.vars.get('typat', [])))}")
        lines.append("")
        lines.append("#----------------------------------------")
        lines.append("# Definition of the planewave basis set")
        lines.append("#----------------------------------------")
        lines.append(f"ecut {self.vars.get('ecut', 42)}")
        if self.vars.get("ecutsm") is not None:
            lines.append(f"ecutsm {self.vars.get('ecutsm')}")
        lines.append("")
        lines.append("#--------------------------")
        lines.append("# Definition of the k-point grid")
        lines.append("#--------------------------")
        lines.append(f"nshiftk {self.vars.get('nshiftk', '1')}")
        lines.append("kptrlatt")
        if self.vars.get("kptrlatt") is not None:
            for row in self.vars.get("kptrlatt"):
                lines.append(f"  {' '.join(map(str, row))}")
        # Make sure to split shiftk if it's a string
        shiftk = self.vars.get("shiftk", "0.5 0.5 0.5")
        if isinstance(shiftk, str):
            shiftk = shiftk.split()
        lines.append(f"shiftk {' '.join(map(str, shiftk))}")
        lines.append(f"nband {self.vars.get('nband')}")
        lines.append("")
        lines.append("#--------------------------")
        lines.append("# Definition of the SCF Procedure")
        lines.append("#--------------------------")
        lines.append(f"nstep {self.vars.get('nstep', 9)}")
        lines.append(f"diemac {self.vars.get('diemac', '1000000.0')}")
        lines.append(f"ixc {self.vars.get('ixc')}")
        conv_criteria = self.vars.get("conv_criteria")
        if conv_criteria is not None:
            conv_value = self.vars.get(conv_criteria)
            lines.append(f"{conv_criteria} {str(conv_value)}")
        pp_dir_path = PseudopotentialManager().folder_path
        lines.append(f'pp_dirpath "{pp_dir_path}"')
        pseudos = self.vars.get("pseudos", [])
        # Remove any embedded double quotes from each pseudo and then join them.
        concatenated_pseudos = ", ".join(pseudo.replace('"', '') for pseudo in pseudos)
        lines.append(f'pseudos "{concatenated_pseudos}"')
        return "\n".join(lines)


