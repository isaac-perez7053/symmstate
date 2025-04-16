<div align="center">
  <img src="images/logo-removebg-preview.png" alt="Project Logo" width="300"/>
</div>

# SymmState

Applications of symmetry in solid state physics 

## Overview

SymmState is a Python package designed to calculate and analyze various symmetry applications within solid-state physics, such as flexoelectric and piezoelectric properties of materials. This package provides seamless interaction with Abinit, allowing users to conduct sophisticated simulations and analyses directly through Python. The package builds off of  many Pymatgen objects for extended functionality. 

## Installation

To install the SymmState package, follow these steps:

1. Install the package using pip:
    ```bash
    pip install symmstate
    ```
3. Download Abinit [here](https://abinit.github.io/abinit_web/) and follow their installation instructions
4. For symmetry-related functionality, download smodes [here](https://iso.byu.edu/iso/isolinux.php)
5. Once downloaded, type 'symmstate' to configure the package to your needs! Look at tests/live for examples of how to use the package.

## Testing

To find some basic tests, run:
```bash
symmstate test --help
```

- Note, some of the tests use the pseudopotentials CaRev.psp8, TiRev.psp8, and ORev.psp8. This will require you to download from the pseudos in the pseudopotential folder before successfully running the tests. 
## Features

- **Symmetry Analysis**: Perform advanced symmetry analysis on solid-state materials.
- **Flexoelectric Properties**: Calculate flexoelectric properties for various materials and their evolution under particular perturbations.
- **Piezoelectric Properties**: Evaluate the piezoelectric response of various materials and evolution under particular perturbations.
- **Abinit Integration**: Interact seamlessly with Abinit for simulations
  
## Future Features

- Extended Abinit interaction and functionality
- Automation of the calculation of symmetry informed phonon dispersion curves
- Extended interaction to Vasp through pymatgen
- Convergence of files using Abinit and Vasp

*More features coming soon!*

---

Feel free to explore and contribute to the development of SymmState as we continue to expand its capabilities for the scientific community interested in solid-state physics.

For any questions or feedback, please don't hesitate to reach out to us at the email isacvillages@gmail.com.
