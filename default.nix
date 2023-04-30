with (import (import ./pinned-nixpkgs.nix) { });

python310Packages.buildPythonPackage {
  src = builtins.path {
    path = ./.;
    name = "travelhook";
  };

  pname = "travelhook";
  version = "0.0.0";

  propagatedBuildInputs =
    (with python310Packages; [ discordpy toml setuptools flask requests ]);
  format = "pyproject";
}
