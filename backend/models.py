from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- Énumérations ---------------------------------------------------------

class Phase(str, Enum):
    NUIT = "nuit"
    DISCUSSION = "discussion"
    VOTE = "vote"


class Equipe(str, Enum):
    VILLAGEOIS = "villageois"
    OUTSIDER = "outsider"
    SBIRE = "sbire"
    DEMON = "demon"


class Alignement(str, Enum):
    BON = "bon"
    MAUVAIS = "mauvais"


class TypeEffet(str, Enum):
    PROTEGE = "protege"
    EMPOISONNE = "empoisonne"
    SONDE = "sonde"
    TUE = "tue"


# --- Temps de la partie ----------------------------------------------------

# Ordre chronologique à l'intérieur d'un tour : la nuit précède le jour.
_ORDRE_PHASE = {Phase.NUIT: 0, Phase.DISCUSSION: 1, Phase.VOTE: 2}


def _instant(tour: int, phase: Phase) -> int:
    """Transforme un couple (tour, phase) en entier croissant, pour comparer deux moments."""
    return tour * 3 + _ORDRE_PHASE[phase]


# Camps du côté du bien. L'outsider est villageois, donc du côté du bien.
_CAMPS_BONS = {Equipe.VILLAGEOIS, Equipe.OUTSIDER}


# --- Rôle : fiche de règles, identique pour tous les joueurs qui ont ce rôle

class Role(BaseModel):
    """Ne contient aucun état de partie : la vie, le pouvoir utilisé ou les effets
    appartiennent au joueur, pas au rôle."""

    model_config = ConfigDict(frozen=True)

    nom: str = Field(min_length=1)
    camp: Equipe
    # None = le rôle n'agit à aucun moment précis.
    phase: Optional[Phase] = None
    # Types d'effets que ce rôle peut produire sur un joueur.
    effets: tuple[TypeEffet, ...] = ()
    # Clés de lien que ce rôle a le droit de poser sur un joueur.
    liens_autorises: tuple[str, ...] = ()
    # Texte affiché au joueur et repris par le skill de l'agent.
    description: str = ""

    @property
    def alignement(self) -> Alignement:
        return Alignement.BON if self.camp in _CAMPS_BONS else Alignement.MAUVAIS


# --- Effet : un effet actif sur un joueur, avec son début et sa fin -------

class Effet(BaseModel):
    """Immutable : tout changement produit un nouvel objet Effet.
    Fin None et None = effet permanent."""

    model_config = ConfigDict(frozen=True)

    type: TypeEffet
    source: str  # rôle ou événement qui a créé l'effet
    tour_debut: int
    phase_debut: Phase
    tour_fin: Optional[int] = None
    phase_fin: Optional[Phase] = None

    @model_validator(mode="after")
    def _fin_coherente(self):
        if (self.tour_fin is None) != (self.phase_fin is None):
            raise ValueError("tour_fin et phase_fin doivent être tous deux renseignés, ou tous deux absents")
        if self.tour_fin is not None and _instant(self.tour_fin, self.phase_fin) <= _instant(self.tour_debut, self.phase_debut):
            raise ValueError("la fin d'un effet doit être postérieure à son début")
        return self

    def est_expire(self, tour: int, phase: Phase) -> bool:
        """Vrai si l'effet doit être retiré à ce moment de la partie."""
        if self.tour_fin is None:
            return False
        return _instant(tour, phase) >= _instant(self.tour_fin, self.phase_fin)




# --- Joueur : état d'une personne dans la partie. Immutable ----------------

class Joueur(BaseModel):
    """Ne contient que l'état du joueur. La fiche de règles reste dans Role."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    nom: str = Field(min_length=1)
    role: Role
    vivant: bool = True
    # Pouvoir déjà utilisé. La remise à zéro éventuelle est gérée par le moteur.
    pouvoir_utilise: bool = False
    # Un joueur mort garde une seule voix pour le reste de la partie.
    vote_fantome: bool = False
    effets: tuple[Effet, ...] = ()
    # Liens vers d'autres joueurs (ex. "maitre", "fausse_piste"). Les clés autorisées sont dans la fiche du rôle.
    liens: dict[str, str] = Field(default_factory=dict)

    @property
    def peut_agir(self) -> bool:
        """Vrai si le joueur a encore un pouvoir disponible. La phase est vérifiée par le moteur."""
        return self.vivant and self.role.phase is not None and not self.pouvoir_utilise

    @property
    def peut_voter(self) -> bool:
        return self.vivant or self.vote_fantome

    def a_effet(self, type_effet: TypeEffet) -> bool:
        return any(e.type == type_effet for e in self.effets)

    def ajouter_effet(self, effet: Effet) -> "Joueur":
        return self.model_copy(update={"effets": self.effets + (effet,)})

    def retirer_effets_expires(self, tour: int, phase: Phase) -> "Joueur":
        restants = tuple(e for e in self.effets if not e.est_expire(tour, phase))
        return self.model_copy(update={"effets": restants})

    def mourir(self) -> "Joueur":
        if not self.vivant:
            raise ValueError(f"{self.nom} est déjà mort")
        return self.model_copy(update={"vivant": False, "vote_fantome": True})

    def utiliser_vote_fantome(self) -> "Joueur":
        if self.vivant or not self.vote_fantome:
            raise ValueError(f"{self.nom} n'a pas de vote fantôme à utiliser")
        return self.model_copy(update={"vote_fantome": False})
    
    def lien(self, cle: str) -> Optional[str]:
        return self.liens.get(cle)

    def avec_lien(self, cle: str, cible_id: str) -> "Joueur":
        """Stocke un lien. Aucune règle ici : elles sont vérifiées par le moteur."""
        return self.model_copy(update={"liens": {**self.liens, cle: cible_id}})



# --- Salon : conversation publique ou privée, historique conservé ----------

class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    auteur_id: str = Field(min_length=1)
    texte: str = Field(min_length=1)
    tour: int
    phase: Phase


class Salon(BaseModel):
    """L'historique n'est jamais supprimé. Un salon fermé reste lisible, mais n'accepte plus de messages."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    nom: str = Field(min_length=1)
    public: bool = False
    membres: tuple[str, ...] = Field(min_length=1)
    messages: tuple[Message, ...] = ()
    ouvert: bool = True

    def est_membre(self, joueur_id: str) -> bool:
        return joueur_id in self.membres

    def messages_visibles_par(self, joueur_id: str) -> tuple[Message, ...]:
        return self.messages if self.est_membre(joueur_id) else ()

    def ajouter_membre(self, joueur_id: str) -> "Salon":
        if not self.ouvert:
            raise ValueError(f"le salon {self.nom} est fermé")
        if self.est_membre(joueur_id):
            raise ValueError(f"{joueur_id} est déjà membre de {self.nom}")
        return self.model_copy(update={"membres": self.membres + (joueur_id,)})

    def ajouter_message(self, message: Message) -> "Salon":
        if not self.ouvert:
            raise ValueError(f"le salon {self.nom} est fermé")
        if not self.est_membre(message.auteur_id):
            raise ValueError(f"{message.auteur_id} n'est pas membre de {self.nom}")
        return self.model_copy(update={"messages": self.messages + (message,)})

    def fermer(self) -> "Salon":
        if not self.ouvert:
            raise ValueError(f"le salon {self.nom} est déjà fermé")
        return self.model_copy(update={"ouvert": False})




# --- Journal : une ligne publique ou privée de l'histoire de la partie -----

class Evenement(BaseModel):
    """public=True : visible de tous. public=False : visible seulement des destinataires.
    Public=False sans destinataire : visible du moteur seul."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(min_length=1)
    tour: int
    phase: Phase
    public: bool = True
    destinataires: tuple[str, ...] = ()

    def visible_par(self, joueur_id: str) -> bool:
        return self.public or joueur_id in self.destinataires


# --- État de la partie : le conteneur de tout le reste ---------------------

class EtatJeu(BaseModel):
    """Ne contient aucune règle. Les règles vivent dans rules_engine."""

    model_config = ConfigDict(frozen=True)

    tour: int = Field(default=1, ge=1)
    phase: Phase = Phase.NUIT
    joueurs: tuple[Joueur, ...] = ()
    salons: tuple[Salon, ...] = ()
    journal: tuple[Evenement, ...] = ()

    @model_validator(mode="after")
    def _identifiants_uniques(self):
        ids_joueurs = [j.id for j in self.joueurs]
        if len(ids_joueurs) != len(set(ids_joueurs)):
            raise ValueError("identifiants de joueurs en double")
        ids_salons = [s.id for s in self.salons]
        if len(ids_salons) != len(set(ids_salons)):
            raise ValueError("identifiants de salons en double")
        return self

    def joueur(self, joueur_id: str) -> Joueur:
        for j in self.joueurs:
            if j.id == joueur_id:
                return j
        raise KeyError(f"joueur inconnu : {joueur_id}")

    def salon(self, salon_id: str) -> Salon:
        for s in self.salons:
            if s.id == salon_id:
                return s
        raise KeyError(f"salon inconnu : {salon_id}")

    def joueurs_vivants(self) -> tuple[Joueur, ...]:
        return tuple(j for j in self.joueurs if j.vivant)

    def remplacer_joueur(self, joueur: Joueur) -> "EtatJeu":
        self.joueur(joueur.id)  # erreur si le joueur n'existe pas
        return self.model_copy(
            update={"joueurs": tuple(joueur if j.id == joueur.id else j for j in self.joueurs)}
        )

    def remplacer_salon(self, salon: Salon) -> "EtatJeu":
        self.salon(salon.id)  # erreur si le salon n'existe pas
        return self.model_copy(
            update={"salons": tuple(salon if s.id == salon.id else s for s in self.salons)}
        )

    def ajouter_evenement(self, evenement: Evenement) -> "EtatJeu":
        return self.model_copy(update={"journal": self.journal + (evenement,)})

    def journal_visible_par(self, joueur_id: str) -> tuple[Evenement, ...]:
        return tuple(e for e in self.journal if e.visible_par(joueur_id))

    def passer_phase(self) -> "EtatJeu":
        """Nuit -> discussion -> vote dans le même tour ; vote -> nuit au tour suivant.
        Retire au passage les effets arrivés à leur fin, pour chaque joueur."""
        suivante = {Phase.NUIT: Phase.DISCUSSION, Phase.DISCUSSION: Phase.VOTE, Phase.VOTE: Phase.NUIT}
        nouvelle_phase = suivante[self.phase]
        nouveau_tour = self.tour + 1 if nouvelle_phase == Phase.NUIT else self.tour
        joueurs = tuple(j.retirer_effets_expires(nouveau_tour, nouvelle_phase) for j in self.joueurs)
        return self.model_copy(update={"tour": nouveau_tour, "phase": nouvelle_phase, "joueurs": joueurs})
    
    def __str__(self) -> str:
        """Résumé lisible de la partie, pour le débogage et les tests."""
        def resume(j: Joueur) -> str:
            effets = ", ".join(e.type.value for e in j.effets)
            return f"{j.nom} ({j.role.nom})" + (f" [{effets}]" if effets else "")

        vivants = [resume(j) for j in self.joueurs if j.vivant]
        morts = [j.nom for j in self.joueurs if not j.vivant]
        lignes = [
            f"Tour {self.tour}, {self.phase.value}",
            f"Vivants ({len(vivants)}) : " + (", ".join(vivants) or "aucun"),
            "Morts : " + (", ".join(morts) or "aucun"),
        ]
        for s in self.salons:
            etat = "ouvert" if s.ouvert else "fermé"
            lignes.append(f"Salon {s.nom} ({etat}, {len(s.membres)} membres, {len(s.messages)} messages)")
        lignes.append(f"Journal : {len(self.journal)} événements")
        return "\n".join(lignes)