{
  description = "budget-cell — PDF budget table extraction pipeline";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;
        pythonPkgs = python.pkgs;

        deps = [
          pythonPkgs.pdfplumber
          pythonPkgs.pymupdf
          pythonPkgs.openpyxl
        ];

        devDeps = [
          pythonPkgs.pytest
        ];

        pythonEnv = python.withPackages (_: deps ++ devDeps);
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv ];
          shellHook = ''
            export PYTHONDONTWRITEBYTECODE=1
          '';
        };

        # nix run .#test
        apps.test = {
          type = "app";
          program = toString (pkgs.writeShellScript "run-tests" ''
            exec ${pythonEnv}/bin/python -m pytest tests/ -q "$@"
          '');
        };

        # nix run .#overlay -- <input.pdf> <output.pdf>
        apps.overlay = {
          type = "app";
          program = toString (pkgs.writeShellScript "run-overlay" ''
            exec ${pythonEnv}/bin/python -m budget_cell.cli.overlay "$@"
          '');
        };
      }
    );
}
