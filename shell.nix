{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = with pkgs; [
    nodejs_22   # npm + node
    python3
    pip-audit
    python3Packages.bandit   # the ci profile needs it; run.py's nix_shell_command stays unwired on purpose
    git
  ];
}