import os
import subprocess
from pathlib import Path
import click
from symmstate.config.settings import settings
from symmstate.pseudopotentials.pseudopotential_manager import PseudopotentialManager
from symmstate.templates.template_manager import TemplateManager
from symmstate.slurm_file import SlurmFile
from symmstate.flpz.energy.energy_program import EnergyProgram
from symmstate.flpz.electrotensor.electro_tensor_program import ElectroTensorProgram
from symmstate.flpz.data_analysis import (
    load_flexo_data,
    plot_energy,
    plot_flexo_components,
    plot_flexo_grid,
    plot_varying_components,
)
import click
import subprocess

# Define the run_smodes function directly here to avoid circular imports.
def run_smodes(smodes_input):
    from symmstate.config.settings import settings  # local import to avoid circularity
    if not Path(settings.SMODES_PATH).is_file():
        raise FileNotFoundError(f"SMODES executable not found at: {settings.SMODES_PATH}")
    command = f"{settings.SMODES_PATH} < {smodes_input} > output.log"
    process = subprocess.run(command, shell=True, capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"SMODES execution failed: {process.stderr}")
    return process.stdout

@click.group()
def cli():
    """SymmState: Applications of symmetry in solid state physics"""

@cli.command()
@click.option("-a", "--add", multiple=True, type=click.Path(), help="Add one or more pseudopotential file paths")
@click.option("-d", "--delete", multiple=True, type=click.Path(), help="Delete one or more pseudopotential file paths")
@click.option("-l", "--list", "list_pseudos", is_flag=True, help="List current pseudopotentials")
def pseudos(add, delete, list_pseudos):
    """Manage pseudopotential folder paths"""
    if (add or delete) and list_pseudos:
        click.echo("Error: Specify only one action at a time (either add, delete, or list).")
        return

    pm = PseudopotentialManager()
    if add:
        for path in add:
            pm.add_pseudopotential(path)
        click.echo("Pseudopotentials added.")
    elif delete:
        for path in delete:
            pm.delete_pseudopotential(path)
        click.echo("Pseudopotentials deleted.")
    elif list_pseudos:
        if pm.pseudo_registry:
            click.echo("Current pseudopotentials:")
            for name, full_path in pm.pseudo_registry.items():
                click.echo(f"{name} -> {full_path}")
        else:
            click.echo("No pseudopotentials found.")
    else:
        click.echo("Error: No action specified. Use --add, --delete, or --list.")

@cli.command()
@click.option("--pp-dir", type=click.Path(), help="Set the pseudopotential directory")
@click.option("--working-dir", type=click.Path(), help="Set the working directory")
@click.option("--ecut", type=int, help="Set default energy cutoff (hartree)")
@click.option("--symm-prec", type=float, help="Set symmetry precision")
@click.option("--kpt-density", type=float, help="Set default k-point density")
@click.option("--slurm-time", type=str, help="Set SLURM time")
@click.option("--slurm-nodes", type=int, help="Set SLURM nodes")
@click.option("--slurm-ntasks", type=int, help="Set SLURM tasks per node")
@click.option("--slurm-mem", type=str, help="Set SLURM memory")
@click.option("--environment", type=str, help="Set environment")
def config(pp_dir, working_dir, ecut, symm_prec, kpt_density, slurm_time, slurm_nodes, slurm_ntasks, slurm_mem, environment):
    """Manage global settings of the package"""
    updated = False
    if pp_dir:
        settings.PP_DIR = Path(pp_dir)
        updated = True
    if working_dir:
        settings.WORKING_DIR = Path(working_dir)
        updated = True
    if ecut:
        settings.DEFAULT_ECUT = ecut
        updated = True
    if symm_prec:
        settings.SYMM_PREC = symm_prec
        updated = True
    if kpt_density:
        settings.DEFAULT_KPT_DENSITY = kpt_density
        updated = True
    if slurm_time:
        settings.SLURM_HEADER["time"] = slurm_time
        updated = True
    if slurm_nodes:
        settings.SLURM_HEADER["nodes"] = slurm_nodes
        updated = True
    if slurm_ntasks:
        settings.SLURM_HEADER["ntasks-per-node"] = slurm_ntasks
        updated = True
    if slurm_mem:
        settings.SLURM_HEADER["mem"] = slurm_mem
        updated = True
    if environment:
        settings.ENVIRONMENT = environment
        updated = True

    if updated:
        click.echo("Settings updated:")
        click.echo(f"PP_DIR: {settings.PP_DIR}")
        click.echo(f"WORKING_DIR: {settings.WORKING_DIR}")
        click.echo(f"DEFAULT_ECUT: {settings.DEFAULT_ECUT}")
        click.echo(f"SYMM_PREC: {settings.SYMM_PREC}")
        click.echo(f"DEFAULT_KPT_DENSITY: {settings.DEFAULT_KPT_DENSITY}")
        click.echo(f"SLURM_HEADER: {settings.SLURM_HEADER}")
        click.echo(f"ENVIRONMENT: {settings.ENVIRONMENT}")
    else:
        click.echo("No settings were updated.")

@cli.command()
@click.option("-a", "--add", multiple=True, type=click.Path(), help="Add a template file path")
@click.option("-d", "--delete", multiple=True, type=click.Path(), help="Delete a template file path")
def templates(add, delete):
    """Manage templates"""
    from symmstate.templates.template_manager import TemplateManager
    if add and delete:
        click.echo("Error: Specify only one action at a time (either add or delete).")
        return

    tm = TemplateManager()
    if add:
        for path in add:
            tm.create_template(path, os.path.basename(path))
        click.echo("Templates added.")
    elif delete:
        for path in delete:
            tm.remove_template(os.path.basename(path))
        click.echo("Templates deleted.")
    else:
        click.echo("Error: No action specified. Use --add or --delete.")

@cli.command()
@click.option("--name", default="EnergyProgram", help="Name of the energy program")
@click.option("--num-datapoints", type=int, default=3, help="Number of perturbed cells to generate")
@click.option("--abi-file", type=click.Path(exists=True), required=True, help="Path to the Abinit file")
@click.option("--min-amp", type=float, default=0.0, help="Minimum amplitude (bohr)")
@click.option("--max-amp", type=float, default=0.5, help="Maximum amplitude (bohr)")
@click.option("--smodes-input", type=click.Path(exists=True), required=True, help="Path to the SMODES input file")
@click.option("--target-irrep", type=str, required=True, help="Target irreducible representation")
@click.option("--unstable-threshold", type=float, default=-20, help="Unstable threshold value")
@click.option("--disp-mag", type=float, default=0.001, help="Displacement magnitude")
def energy(name, num_datapoints, abi_file, min_amp, max_amp, smodes_input, target_irrep, unstable_threshold, disp_mag):
    """
    Run the Energy Program.
    
    Required inputs:
      - abi-file: Path to a valid Abinit file.
      - smodes-input: Path to the SMODES input file.
      - target-irrep: Target irreducible representation.
      
    Other parameters (with defaults) can be adjusted via options.
    """
    click.echo("Running Energy Program with the following parameters:")
    click.echo(f"Name: {name}")
    click.echo(f"Number of datapoints: {num_datapoints}")
    click.echo(f"Abinit file: {abi_file}")
    click.echo(f"SMODES input: {smodes_input}")
    click.echo(f"Target irreducible representation: {target_irrep}")
    click.echo(f"Min amplitude: {min_amp}")
    click.echo(f"Max amplitude: {max_amp}")
    click.echo(f"Displacement magnitude: {disp_mag}")
    click.echo(f"Unstable threshold: {unstable_threshold}")

    # Create a SlurmFile object using the SLURM header from settings.
    slurm_header = "".join(f"#SBATCH --{key}={value}\n" for key, value in settings.SLURM_HEADER.items())
    slurm_obj = SlurmFile(sbatch_header_source=slurm_header, num_processors=1)
    
    energy_prog = EnergyProgram(
        name=name,
        num_datapoints=num_datapoints,
        abi_file=abi_file,
        min_amp=min_amp,
        max_amp=max_amp,
        smodes_input=smodes_input,
        target_irrep=target_irrep,
        slurm_obj=slurm_obj,
        symm_prec=settings.SYMM_PREC,
        disp_mag=disp_mag,
        unstable_threshold=unstable_threshold,
    )
    energy_prog.run_program()

@cli.command()
@click.option("--name", default="ElectroTensorProgram", help="Name of the electrotensor program")
@click.option("--num-datapoints", type=int, default=3, help="Number of perturbed cells to generate")
@click.option("--abi-file", type=click.Path(exists=True), required=True, help="Path to the Abinit file")
@click.option("--min-amp", type=float, default=0.0, help="Minimum amplitude (bohr)")
@click.option("--max-amp", type=float, default=0.5, help="Maximum amplitude (bohr)")
@click.option("--smodes-input", type=click.Path(exists=True), required=True, help="Path to the SMODES input file")
@click.option("--target-irrep", type=str, required=True, help="Target irreducible representation")
@click.option("--unstable-threshold", type=float, default=-20, help="Unstable threshold value")
@click.option("--disp-mag", type=float, default=0.001, help="Displacement magnitude")
@click.option("--piezo", is_flag=True, help="Run piezoelectric calculations instead of flexoelectric")
def electrotensor(name, num_datapoints, abi_file, min_amp, max_amp, smodes_input, target_irrep, unstable_threshold, disp_mag, piezo):
    """
    Run the ElectroTensor Program.
    
    Required inputs:
      - abi-file: Path to a valid Abinit file.
      - smodes-input: Path to the SMODES input file.
      - target-irrep: Target irreducible representation.
      
    Other parameters (with defaults) can be adjusted via options.
    """
    click.echo("Running ElectroTensor Program with the following parameters:")
    click.echo(f"Name: {name}")
    click.echo(f"Number of datapoints: {num_datapoints}")
    click.echo(f"Abinit file: {abi_file}")
    click.echo(f"SMODES input: {smodes_input}")
    click.echo(f"Target irreducible representation: {target_irrep}")
    click.echo(f"Min amplitude: {min_amp}")
    click.echo(f"Max amplitude: {max_amp}")
    click.echo(f"Displacement magnitude: {disp_mag}")
    click.echo(f"Unstable threshold: {unstable_threshold}")
    click.echo(f"Piezo calculation: {piezo}")

    slurm_header = "".join(f"#SBATCH --{key}={value}\n" for key, value in settings.SLURM_HEADER.items())
    slurm_obj = SlurmFile(sbatch_header_source=slurm_header, num_processors=1)
    
    et_prog = ElectroTensorProgram(
        name=name,
        num_datapoints=num_datapoints,
        abi_file=abi_file,
        min_amp=min_amp,
        max_amp=max_amp,
        smodes_input=smodes_input,
        target_irrep=target_irrep,
        slurm_obj=slurm_obj,
        symm_prec=settings.SYMM_PREC,
        disp_mag=disp_mag,
        unstable_threshold=unstable_threshold,
        piezo_calculation=piezo
    )
    et_prog.run_program()

@cli.command()
@click.option("--smodes-input", type=click.Path(exists=True), required=True,
              help="Path to the SMODES input file")
def smodes(smodes_input):
    """
    Run SMODES using the provided SMODES input file.
    
    This command uses the global SMODES path from settings.
    """
    click.echo("Running SMODES...")
    try:
        result = run_smodes(smodes_input)
        click.echo("SMODES output:")
        click.echo(result)
    except Exception as e:
        click.echo(f"Error running SMODES: {e}")

@cli.group()
def test():
    """Run test suites for individual modules using pytest"""
    pass

@test.command()
def abinit_file():
    """Run tests for test_abinit_file.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_abinit_file.py")], check=True)

@test.command()
def abinit_unit_cell():
    """Run tests for test_abinit_unit_cell.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_abinit_unit_cell.py")], check=True)

@test.command()
def electrotensor():
    """Run tests for test_electro_tensor.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_electro_tensor.py")], check=True)

@test.command()
def energy_program():
    """Run tests for test_energy_program.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_energy_program.py")], check=True)

@test.command()
def perturbations():
    """Run tests for test_perturbations.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_perturbations.py")], check=True)

@test.command()
def pseudopotential():
    """Run tests for test_pseudopotential.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_pseudopotential.py")], check=True)

@test.command()
def slurm_jobs():
    """Run tests for test_slurm_jobs.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_slurm_jobs.py")], check=True)

@test.command()
def smodes_calculator():
    """Run tests for test_smodes_calculator.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_smodes_calculator.py")], check=True)

@test.command()
def template_manager():
    """Run tests for test_template_manager.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_template_manager.py")], check=True)

@test.command()
def unit_cell_module():
    """Run tests for test_unit_cell_module.py"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir / "test_unit_cell_module.py")], check=True)

@test.command()
def test_all():
    """Run all tests at once using pytest discovery"""
    test_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "unit"
    subprocess.run(["pytest", str(test_dir)], check=True)

@cli.command()
@click.option("--results-file", type=click.Path(exists=True), required=True,
              help="Path to the results file produced by a perturbation run")
@click.option("--analysis-type", type=click.Choice(["energy", "flexo", "grid", "varying"]),
              required=True, help="Type of data analysis to perform")
@click.option("--save", is_flag=True, help="Save the generated plot to a file")
@click.option("--filename", default="analysis_plot", help="Filename for the saved plot")
@click.option("--threshold", type=float, default=None,
              help="Threshold value for 'varying' analysis (optional)")
def data_analysis(results_file, analysis_type, save, filename, threshold):
    """Perform data analysis on a results file produced by a perturbation run."""
    amplitudes, energies, flexo_amps, flexo_tensors = load_flexo_data(results_file)

    if analysis_type == "energy":
        ax = plot_energy(amplitudes, energies)
    elif analysis_type == "flexo":
        ax = plot_flexo_components(flexo_amps, flexo_tensors)
    elif analysis_type == "grid":
        fig = plot_flexo_grid(flexo_amps, flexo_tensors)
    elif analysis_type == "varying":
        fig = plot_varying_components(flexo_amps, flexo_tensors, threshold=threshold)
    
    if save:
        if analysis_type in ["flexo", "grid", "varying"]:
            if analysis_type == "grid":
                fig.savefig(f"{filename}_grid.png", bbox_inches="tight")
                click.echo(f"Grid plot saved as {filename}_grid.png")
            elif analysis_type == "varying":
                fig.savefig(f"{filename}_varying.png", bbox_inches="tight")
                click.echo(f"Varying components plot saved as {filename}_varying.png")
            else:
                ax.get_figure().savefig(f"{filename}_flexo.png", bbox_inches="tight")
                click.echo(f"Flexoelectric plot saved as {filename}_flexo.png")
        else:
            ax.get_figure().savefig(f"{filename}_energy.png", bbox_inches="tight")
            click.echo(f"Energy plot saved as {filename}_energy.png")
    else:
        if analysis_type in ["flexo", "grid", "varying"]:
            fig.show()
        else:
            ax.get_figure().show()

if __name__ == "__main__":
    cli()



