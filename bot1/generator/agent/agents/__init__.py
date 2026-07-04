"""LLM-gestützte Unter-Agenten für das AI-OS.

Original: Architect (plant Tools), Coder (schreibt Code), Fixer (repariert).
Erweitert: Researcher (recherchiert), Deployer (bringt live).
"""
from .architect import ArchitectAgent
from .coder import CoderAgent
from .deployer import DeployAgent
from .fixer import FixerAgent
from .researcher import ResearcherAgent

__all__ = [
    "ArchitectAgent",
    "CoderAgent",
    "DeployAgent",
    "FixerAgent",
    "ResearcherAgent",
]
