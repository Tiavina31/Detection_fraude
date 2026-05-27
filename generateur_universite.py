import random
import math
import time
from neo4j import GraphDatabase
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

URI_NEO4J    = "bolt://localhost:7687"
UTILISATEUR  = "neo4j"
MOT_DE_PASSE = "password123"

# Chemin vers le fichier des personnes
FICHIER_PERSONNES = "personnes.txt"

# Pourcentage du réseau de drogue (réaliste = 3 à 8%)
POURCENTAGE_RESEAU = 0.05   # 5%

POIDS_SIGNAUX = {
    "rencontre_discrete" : 0.2,
    "contact_frequent"   : 0.2,
    "meme_lieu_suspect"  : 0.3,
    "echange_objet"      : 0.5,
    "transfert_argent"   : 0.7,
}

COULEURS = {
    "fournisseur"   : "#e74c3c",   # Rouge vif
    "consommateur"  : "#2ecc71",   # Vert
    "intermediaire" : "#f39c12",   # Orange
    "suspect"       : "#e67e22",   # Orange foncé
    "innocent"      : "#3498db",   # Bleu
}


# ═══════════════════════════════════════════════════════════════
# 1. LECTURE DU FICHIER PERSONNES.TXT
# ═══════════════════════════════════════════════════════════════

def lire_fichier_personnes(chemin_fichier):
    """
    Lit le fichier personnes.txt et retourne la liste des personnes.

    Format attendu de chaque ligne (non commentaire) :
        identifiant|nom_complet|prenom|filiere|annee|age

    Exemple :
        P000001|Michel Garcia|Michel|Informatique|M2|33

    Les lignes commençant par # sont ignorées (commentaires).
    Les lignes vides sont ignorées.

    Retourne une liste de dictionnaires, une par personne.
    """

    personnes          = []
    nb_lignes_lues     = 0
    nb_lignes_ignorees = 0
    nb_erreurs         = 0

    print(f"📂 Lecture du fichier : {chemin_fichier}")

    try:
        with open(chemin_fichier, "r", encoding="utf-8") as fichier:

            for numero_ligne, ligne in enumerate(fichier, start=1):

                # Nettoyer la ligne (supprimer espaces et retours chariot)
                ligne = ligne.strip()

                # Ignorer les lignes vides
                if not ligne:
                    nb_lignes_ignorees += 1
                    continue

                # Ignorer les commentaires (lignes commençant par #)
                if ligne.startswith("#"):
                    nb_lignes_ignorees += 1
                    continue

                # Découper la ligne par le séparateur |
                parties = ligne.split("|")

                # Vérifier qu'on a bien exactement 6 champs
                if len(parties) != 6:
                    print(f"   ⚠️  Ligne {numero_ligne} ignorée "
                          f"({len(parties)} champs trouvés au lieu de 6) : '{ligne}'")
                    nb_erreurs += 1
                    continue

                # Extraire chaque champ
                identifiant, nom_complet, prenom, filiere, annee, age_str = parties

                # Valider et convertir l'âge en nombre entier
                try:
                    age = int(age_str.strip())
                except ValueError:
                    print(f"   ⚠️  Ligne {numero_ligne} : âge invalide '{age_str}' — ignorée")
                    nb_erreurs += 1
                    continue

                # Construire le dictionnaire de la personne
                # Tous les champs sont nettoyés avec .strip()
                personne = {
                    "identifiant"     : identifiant.strip(),
                    "nom_complet"     : nom_complet.strip(),
                    "prenom"          : prenom.strip(),
                    "filiere"         : filiere.strip(),
                    "annee"           : annee.strip(),
                    "age"             : age,
                    # Champs calculés plus tard — initialisés à innocent
                    "role"            : "innocent",
                    "score_suspicion" : 0.0,
                    "observations"    : [],
                    "dans_reseau"     : False
                }

                personnes.append(personne)
                nb_lignes_lues += 1

    except FileNotFoundError:
        print(f"\n❌ ERREUR : Fichier '{chemin_fichier}' introuvable.")
        print(f"   Vérifie que le fichier est dans le même dossier que ce script.")
        raise SystemExit(1)

    except PermissionError:
        print(f"\n❌ ERREUR : Permission refusée pour lire '{chemin_fichier}'.")
        raise SystemExit(1)

    # Résumé de la lecture
    print(f"   ✅ {nb_lignes_lues} personnes chargées")
    if nb_lignes_ignorees > 0:
        print(f"   ℹ️  {nb_lignes_ignorees} lignes ignorées (commentaires / vides)")
    if nb_erreurs > 0:
        print(f"   ⚠️  {nb_erreurs} lignes avec erreurs ignorées")
    print()

    return personnes


# ═══════════════════════════════════════════════════════════════
# 2. CONNEXION NEO4J
# ═══════════════════════════════════════════════════════════════

class ConnexionNeo4j:
    def __init__(self, uri, utilisateur, mot_de_passe):
        self.driver = GraphDatabase.driver(uri, auth=(utilisateur, mot_de_passe))
        print("✅ Connexion à Neo4j réussie")

    def fermer(self):
        self.driver.close()
        print("🔒 Connexion Neo4j fermée")

    def executer(self, requete, parametres=None):
        with self.driver.session() as session:
            resultat = session.run(requete, parametres or {})
            return resultat.data()


# ═══════════════════════════════════════════════════════════════
# 3. GÉNÉRATEUR DU RÉSEAU DE DROGUE RÉALISTE
# ═══════════════════════════════════════════════════════════════

def generer_reseau_drogue(toutes_personnes, pourcentage):
    """
    Génère un réseau de drogue réaliste avec une hiérarchie :

    NIVEAU 0 : Gros fournisseurs  → fournissent les intermédiaires
    NIVEAU 1 : Intermédiaires     → achètent et revendent
    NIVEAU 2 : Petits revendeurs  → revendent aux consommateurs
    NIVEAU 3 : Consommateurs      → achètent seulement
    """
    nb_total  = len(toutes_personnes)
    nb_reseau = int(nb_total * pourcentage)

    # Sélectionner aléatoirement les membres du réseau
    membres_reseau = random.sample(toutes_personnes, nb_reseau)

    # Répartition hiérarchique réaliste
    nb_gros_fournisseurs = max(2, nb_reseau // 50)
    nb_intermediaires    = max(3, nb_reseau // 10)
    nb_revendeurs        = nb_reseau // 4
    nb_consommateurs     = nb_reseau - nb_gros_fournisseurs - nb_intermediaires - nb_revendeurs

    gros_fournisseurs = membres_reseau[:nb_gros_fournisseurs]
    intermediaires    = membres_reseau[nb_gros_fournisseurs:
                                       nb_gros_fournisseurs + nb_intermediaires]
    revendeurs        = membres_reseau[nb_gros_fournisseurs + nb_intermediaires:
                                       nb_gros_fournisseurs + nb_intermediaires + nb_revendeurs]
    consommateurs     = membres_reseau[nb_gros_fournisseurs + nb_intermediaires + nb_revendeurs:]

    transactions = []

    # Gros fournisseurs → intermédiaires
    for fournisseur in gros_fournisseurs:
        cibles = random.sample(intermediaires,
                               min(len(intermediaires), random.randint(3, 7)))
        for cible in cibles:
            transactions.append({
                "source"      : fournisseur["identifiant"],
                "cible"       : cible["identifiant"],
                "type_signal" : random.choice(["transfert_argent", "echange_objet"]),
                "poids"       : random.randint(3, 8)
            })

    # Intermédiaires → revendeurs
    for intermediaire in intermediaires:
        cibles = random.sample(revendeurs,
                               min(len(revendeurs), random.randint(2, 5)))
        for cible in cibles:
            transactions.append({
                "source"      : intermediaire["identifiant"],
                "cible"       : cible["identifiant"],
                "type_signal" : random.choice(["echange_objet", "rencontre_discrete"]),
                "poids"       : random.randint(2, 5)
            })

    # Revendeurs → consommateurs
    for revendeur in revendeurs:
        nb_clients = random.randint(1, 5)
        clients    = random.sample(consommateurs,
                                   min(len(consommateurs), nb_clients))
        for client in clients:
            transactions.append({
                "source"      : revendeur["identifiant"],
                "cible"       : client["identifiant"],
                "type_signal" : random.choice(["contact_frequent",
                                               "meme_lieu_suspect",
                                               "echange_objet"]),
                "poids"       : random.randint(1, 4)
            })

    print(f"🏗️  Structure du réseau généré ({nb_reseau} personnes sur {nb_total}) :")
    print(f"   Gros fournisseurs : {len(gros_fournisseurs)}")
    print(f"   Intermédiaires    : {len(intermediaires)}")
    print(f"   Revendeurs        : {len(revendeurs)}")
    print(f"   Consommateurs     : {len(consommateurs)}")
    print(f"   Transactions      : {len(transactions)}\n")

    return transactions


# ═══════════════════════════════════════════════════════════════
# 4. INITIALISATION DANS NEO4J (PAR LOTS POUR LA PERFORMANCE)
# ═══════════════════════════════════════════════════════════════

def initialiser_universite_neo4j(connexion, toutes_personnes):
    """
    Vide la base et insère toutes les personnes du fichier.txt dans Neo4j.
    Utilise des lots de 500 pour ne pas saturer la mémoire.
    """
    print("🗑️  Nettoyage de la base Neo4j...")
    connexion.executer("MATCH (n) DETACH DELETE n")

    nb = len(toutes_personnes)
    print(f"👥 Insertion de {nb:,} personnes dans Neo4j...")

    taille_lot = 500
    for i in range(0, nb, taille_lot):
        lot = toutes_personnes[i:i + taille_lot]
        connexion.executer("""
            UNWIND $batch AS p
            CREATE (:Personne {
                identifiant     : p.identifiant,
                nom_complet     : p.nom_complet,
                prenom          : p.prenom,
                filiere         : p.filiere,
                annee           : p.annee,
                age             : p.age,
                role            : p.role,
                score_suspicion : p.score_suspicion,
                dans_reseau     : p.dans_reseau,
                observations    : p.observations
            })
        """, {"batch": lot})
        print(f"   ✔ {min(i + taille_lot, nb):,} / {nb:,} insérées")

    # Index pour accélérer les MATCH par identifiant
    connexion.executer(
        "CREATE INDEX personne_id IF NOT EXISTS "
        "FOR (p:Personne) ON (p.identifiant)"
    )
    print("✅ Index créé\n")


def inserer_transactions_neo4j(connexion, transactions):
    """
    Insère toutes les transactions (liens du réseau) dans Neo4j.
    Met à jour les observations et le flag dans_reseau sur chaque nœud.
    """
    print(f"🔗 Insertion de {len(transactions)} transactions...")

    taille_lot = 200
    for i in range(0, len(transactions), taille_lot):
        lot = transactions[i:i + taille_lot]
        connexion.executer("""
            UNWIND $batch AS t
            MATCH (a:Personne {identifiant: t.source})
            MATCH (b:Personne {identifiant: t.cible})
            MERGE (a)-[r:INTERACTION {type_signal: t.type_signal}]->(b)
            ON CREATE SET r.poids = t.poids
            ON MATCH  SET r.poids = r.poids + t.poids
        """, {"batch": lot})

    # Propager les observations sur les nœuds depuis les relations
    connexion.executer("""
        MATCH (a:Personne)-[r:INTERACTION]->(b:Personne)
        SET a.observations = a.observations + [r.type_signal],
            b.observations = b.observations + [r.type_signal],
            a.dans_reseau  = true,
            b.dans_reseau  = true
    """)
    print("✅ Transactions insérées\n")


# ═══════════════════════════════════════════════════════════════
# 5. CHARGEMENT NEO4J → NETWORKX POUR LES CALCULS
# ═══════════════════════════════════════════════════════════════

def charger_graphe_depuis_neo4j(connexion):
    """
    Lit tous les nœuds et relations depuis Neo4j
    et reconstruit un graphe NetworkX pour les calculs mathématiques.

    Neo4j  = stockage persistant
    NetworkX = moteur de calcul (PageRank, centralité...)
    """
    print("📥 Chargement Neo4j → NetworkX...")
    graphe = nx.DiGraph()

    # Charger les nœuds
    noeuds = connexion.executer("""
        MATCH (p:Personne)
        RETURN p.identifiant     AS id,
               p.nom_complet     AS nom,
               p.role            AS role,
               p.score_suspicion AS score,
               p.observations    AS observations,
               p.dans_reseau     AS dans_reseau
    """)
    for n in noeuds:
        graphe.add_node(
            n['id'],
            nom          = n['nom'],
            role         = n['role'],
            score        = n['score'],
            observations = n['observations'] or [],
            dans_reseau  = n['dans_reseau']
        )

    # Charger les relations
    relations = connexion.executer("""
        MATCH (a:Personne)-[r:INTERACTION]->(b:Personne)
        RETURN a.identifiant AS source,
               b.identifiant AS cible,
               r.poids       AS poids,
               r.type_signal AS type_signal
    """)
    for r in relations:
        graphe.add_edge(
            r['source'], r['cible'],
            poids       = r['poids'],
            type_signal = r['type_signal']
        )

    print(f"   Nœuds    : {graphe.number_of_nodes():,}")
    print(f"   Relations: {graphe.number_of_edges():,}\n")
    return graphe


# ═══════════════════════════════════════════════════════════════
# 6. CALCUL DES SCORES DE SUSPICION
# ═══════════════════════════════════════════════════════════════

def calculer_scores(graphe):
    """
    Calcule un score entre 0 et 1 pour chaque personne.
    Travaille uniquement sur le sous-graphe du réseau (performance).
    """
    print("📊 Calcul des scores de suspicion...")

    if graphe.number_of_edges() == 0:
        print("   Aucune relation trouvée — scores à 0\n")
        return

    # Isoler le sous-graphe des personnes dans le réseau
    noeuds_reseau = [n for n, d in graphe.nodes(data=True)
                     if d.get('dans_reseau')]
    sous_graphe   = graphe.subgraph(noeuds_reseau)

    if len(sous_graphe.nodes()) == 0:
        return

    centralite = nx.betweenness_centrality(sous_graphe, weight='poids')
    pagerank   = nx.pagerank(sous_graphe, weight='poids')
    nb         = len(sous_graphe.nodes())

    for noeud in graphe.nodes():
        obs = graphe.nodes[noeud]['observations']

        # Score basé sur les types de signaux observés (60%)
        score_signaux = sum(POIDS_SIGNAUX.get(s, 0.1) for s in obs)
        score_signaux = min(score_signaux, 1.0)

        # Score basé sur la position dans le réseau (40%)
        score_reseau = (
            centralite.get(noeud, 0) * 0.4 +
            pagerank.get(noeud, 0) * nb * 0.3 +
            (sous_graphe.degree(noeud) / max(nb - 1, 1)) * 0.3
        )
        score_reseau = min(score_reseau, 1.0)

        score_final = (score_signaux * 0.6) + (score_reseau * 0.4)
        graphe.nodes[noeud]['score'] = round(score_final, 3)

    print("✅ Scores calculés\n")


# ═══════════════════════════════════════════════════════════════
# 7. CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classifier(graphe,
               seuil_fournisseur  = 3,
               seuil_consommateur = 2,
               seuil_mini         = 0.15):
    """
    Attribue un rôle définitif à chaque personne
    en combinant son score de suspicion et ses degrés.
    """
    print("🏷️  Classification des personnes...")

    for noeud in graphe.nodes():
        score   = graphe.nodes[noeud]['score']
        deg_out = graphe.out_degree(noeud)
        deg_in  = graphe.in_degree(noeud)

        if score < seuil_mini:
            graphe.nodes[noeud]['role'] = "innocent"
        elif deg_out >= seuil_fournisseur and deg_in >= seuil_consommateur:
            graphe.nodes[noeud]['role'] = "intermediaire"
        elif deg_out >= seuil_fournisseur:
            graphe.nodes[noeud]['role'] = "fournisseur"
        elif deg_in >= seuil_consommateur:
            graphe.nodes[noeud]['role'] = "consommateur"
        else:
            graphe.nodes[noeud]['role'] = "suspect"

    print("✅ Classification terminée\n")


# ═══════════════════════════════════════════════════════════════
# 8. SAUVEGARDE DES RÉSULTATS DANS NEO4J
# ═══════════════════════════════════════════════════════════════

def sauvegarder_dans_neo4j(connexion, graphe):
    """
    Renvoie les scores et rôles calculés par NetworkX vers Neo4j.
    """
    print("💾 Sauvegarde des résultats dans Neo4j...")

    donnees    = [
        {"id": n, "role": d['role'], "score": d['score']}
        for n, d in graphe.nodes(data=True)
    ]
    taille_lot = 500

    for i in range(0, len(donnees), taille_lot):
        lot = donnees[i:i + taille_lot]
        connexion.executer("""
            UNWIND $batch AS d
            MATCH (p:Personne {identifiant: d.id})
            SET p.role            = d.role,
                p.score_suspicion = d.score
        """, {"batch": lot})

    print("✅ Résultats sauvegardés\n")


# ═══════════════════════════════════════════════════════════════
# 9. RAPPORT FINAL
# ═══════════════════════════════════════════════════════════════

def afficher_rapport(connexion):
    """
    Lit les résultats depuis Neo4j et affiche un rapport complet.
    """
    print("\n" + "=" * 65)
    print("         RAPPORT D'ANALYSE DU RÉSEAU UNIVERSITAIRE")
    print("=" * 65)

    emojis = {
        "fournisseur"   : "🔴",
        "consommateur"  : "🟢",
        "intermediaire" : "🟡",
        "suspect"       : "🟠",
        "innocent"      : "🔵",
    }

    for role in ["fournisseur", "intermediaire", "consommateur", "suspect", "innocent"]:
        res = connexion.executer("""
            MATCH (p:Personne {role: $role})
            RETURN count(p)              AS nb,
                   avg(p.score_suspicion) AS score_moyen,
                   max(p.score_suspicion) AS score_max
        """, {"role": role})

        nb        = res[0]['nb']
        score_moy = res[0]['score_moyen'] or 0
        score_max = res[0]['score_max']   or 0

        if nb > 0:
            print(f"\n{emojis[role]} {role.upper()}S : {nb:,} personnes")
            if role != "innocent":
                print(f"   Score moyen : {score_moy:.3f}  |  Score max : {score_max:.3f}")
                # Top 3 les plus suspects
                top = connexion.executer("""
                    MATCH (p:Personne {role: $role})
                    RETURN p.nom_complet     AS nom,
                           p.filiere         AS filiere,
                           p.annee           AS annee,
                           p.score_suspicion AS score
                    ORDER BY p.score_suspicion DESC LIMIT 3
                """, {"role": role})
                for p in top:
                    print(f"   • {p['nom']:25s} | {p['filiere']:15s} "
                          f"| {p['annee']:10s} | Score: {p['score']:.3f}")

    # Statistiques globales
    stats = connexion.executer("""
        MATCH (p:Personne)
        RETURN count(p) AS total,
               sum(CASE WHEN p.role = 'innocent'  THEN 1 ELSE 0 END) AS innocents,
               sum(CASE WHEN p.role <> 'innocent' THEN 1 ELSE 0 END) AS impliques
    """)[0]

    total     = stats['total']
    innocents = stats['innocents']
    impliques = stats['impliques']

    print(f"\n{'=' * 65}")
    print(f"  TOTAL UNIVERSITÉ  : {total:,} personnes")
    print(f"  Réseau de drogue  : {impliques:,}  ({impliques * 100 // total}%)")
    print(f"  Innocents         : {innocents:,}  ({innocents * 100 // total}%)")
    print(f"{'=' * 65}\n")


# ═══════════════════════════════════════════════════════════════
# 10. VISUALISATION AVEC COULEURS PAR RÔLE
# ═══════════════════════════════════════════════════════════════

def visualiser_graphe(graphe, nb_personnes):
    """
    Génère une visualisation en deux parties :
    - Gauche  : graphe du réseau (réseau au centre, innocents en périphérie)
    - Droite  : camembert de la répartition des rôles
    Chaque rôle a sa couleur distincte.
    """
    print("🎨 Génération de la visualisation...")

    roles  = nx.get_node_attributes(graphe, 'role')
    scores = nx.get_node_attributes(graphe, 'score')

    # Grouper les nœuds par rôle
    groupes = {role: [] for role in COULEURS}
    for noeud, role in roles.items():
        groupes.get(role, groupes["innocent"]).append(noeud)

    noeuds_reseau    = [n for n in graphe.nodes() if roles.get(n) != "innocent"]
    noeuds_innocents = groupes["innocent"]

    # Échantillonner les innocents pour la lisibilité (max 150 affichés)
    echantillon_innocents = random.sample(
        noeuds_innocents,
        min(150, len(noeuds_innocents))
    )
    noeuds_visibles = noeuds_reseau + echantillon_innocents
    sous_graphe_vis = graphe.subgraph(noeuds_visibles)

    fig, axes = plt.subplots(1, 2, figsize=(24, 12), facecolor="#0d1117")
    fig.suptitle(
        f"Analyse du Réseau Cannabis — Université ({nb_personnes:,} personnes)",
        fontsize=17, color="white", fontweight="bold", y=0.98
    )

    # ── AXE GAUCHE : graphe ─────────────────────────────────────
    ax1 = axes[0]
    ax1.set_facecolor("#0d1117")
    ax1.set_title(
        "Réseau de distribution\n"
        f"(réseau complet + {len(echantillon_innocents)} innocents échantillonnés)",
        color="#aaaaaa", fontsize=11, pad=12
    )

    # Calculer les positions
    position = {}
    if noeuds_reseau:
        sg_reseau = graphe.subgraph(noeuds_reseau)
        pos_r     = nx.spring_layout(sg_reseau, seed=42,
                                     k=2.5, iterations=80, scale=2.2)
        position.update(pos_r)

    nb_inn = len(echantillon_innocents)
    for i, innocent in enumerate(echantillon_innocents):
        angle = 2 * math.pi * i / max(nb_inn, 1)
        rayon = 3.9 + random.uniform(-0.25, 0.25)
        position[innocent] = (rayon * math.cos(angle),
                              rayon * math.sin(angle))

    # Dessiner couche par couche (innocents d'abord, fournisseurs en dernier)
    ordre_dessin = ["innocent", "suspect", "consommateur", "intermediaire", "fournisseur"]
    for role in ordre_dessin:
        noeuds_role = [n for n in sous_graphe_vis.nodes()
                       if roles.get(n) == role and n in position]
        if not noeuds_role:
            continue

        if role == "innocent":
            tailles = [100] * len(noeuds_role)
            alpha   = 0.25
        else:
            tailles = [250 + scores.get(n, 0) * 900 for n in noeuds_role]
            alpha   = 0.93

        nx.draw_networkx_nodes(
            sous_graphe_vis, position,
            nodelist   = noeuds_role,
            node_color = COULEURS[role],
            node_size  = tailles,
            alpha      = alpha,
            ax         = ax1
        )

    # Étiquettes uniquement pour le réseau (lisibilité)
    labels_reseau = {
        n: graphe.nodes[n].get('nom', n)[:12]
        for n in noeuds_reseau if n in position
    }
    nx.draw_networkx_labels(
        sous_graphe_vis, position,
        labels      = labels_reseau,
        font_size   = 5,
        font_color  = "white",
        font_weight = "bold",
        ax          = ax1
    )

    # Arêtes
    aretes = [(u, v) for u, v in sous_graphe_vis.edges()
              if u in position and v in position]
    if aretes:
        poids_aretes = [sous_graphe_vis[u][v].get('poids', 1) for u, v in aretes]
        nx.draw_networkx_edges(
            sous_graphe_vis, position,
            edgelist        = aretes,
            width           = [min(p * 0.3, 2.5) for p in poids_aretes],
            edge_color      = "#e74c3c",
            alpha           = 0.45,
            arrows          = True,
            arrowsize       = 8,
            connectionstyle = "arc3,rad=0.1",
            ax              = ax1
        )

    ax1.axis("off")

    # ── AXE DROIT : camembert ───────────────────────────────────
    ax2 = axes[1]
    ax2.set_facecolor("#0d1117")
    ax2.set_title("Répartition des rôles", color="#aaaaaa", fontsize=11, pad=12)

    comptage           = {role: len(noeuds) for role, noeuds in groupes.items()}
    roles_affiches     = [r for r, n in comptage.items() if n > 0]
    valeurs            = [comptage[r] for r in roles_affiches]
    couleurs_camembert = [COULEURS[r] for r in roles_affiches]

    wedge_props = {"linewidth": 2, "edgecolor": "#0d1117"}
    explode     = [0.05] * len(roles_affiches)

    wedges, texts, autotexts = ax2.pie(
        valeurs,
        colors      = couleurs_camembert,
        autopct     = lambda p: (
            f"{p:.1f}%\n({int(round(p * nb_personnes / 100)):,})"
            if p > 0.5 else ""
        ),
        startangle  = 140,
        explode     = explode,
        wedgeprops  = wedge_props,
        pctdistance = 0.72
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(9)
        at.set_fontweight("bold")

    # Légende détaillée
    elements_legende = [
        mpatches.Patch(
            color = COULEURS[r],
            label = f"{r.capitalize():15s}  {comptage[r]:>6,}  "
                    f"({comptage[r] * 100 / nb_personnes:.1f}%)"
        )
        for r in roles_affiches
    ]
    ax2.legend(
        handles        = elements_legende,
        loc            = "lower center",
        bbox_to_anchor = (0.5, -0.18),
        fontsize       = 10.5,
        framealpha     = 0.15,
        facecolor      = "#1a1f2e",
        edgecolor      = "#444",
        labelcolor     = "white"
    )

    # Texte central du camembert
    ax2.text(0, 0,
             f"{nb_personnes:,}\npersonnes",
             ha="center", va="center",
             fontsize=14, color="white", fontweight="bold")

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    chemin = "reseau_universite.png"
    plt.savefig(chemin, dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close()
    print(f"✅ Visualisation sauvegardée → {chemin}\n")
    return chemin


# ═══════════════════════════════════════════════════════════════
# 11. PROGRAMME PRINCIPAL
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    debut = time.time()

    print("\n" + "=" * 65)
    print("   DÉTECTION RÉSEAU CANNABIS — CHARGEMENT DEPUIS FICHIER TXT")
    print("=" * 65 + "\n")

    # ── ÉTAPE 1 : Lire le fichier personnes.txt ────────────────
    toutes_personnes = lire_fichier_personnes(FICHIER_PERSONNES)
    nb_personnes     = len(toutes_personnes)

    # ── ÉTAPE 2 : Générer le réseau de drogue ──────────────────
    transactions = generer_reseau_drogue(toutes_personnes, POURCENTAGE_RESEAU)

    # ── ÉTAPE 3 : Connexion et insertion dans Neo4j ────────────
    connexion = ConnexionNeo4j(URI_NEO4J, UTILISATEUR, MOT_DE_PASSE)

    try:
        initialiser_universite_neo4j(connexion, toutes_personnes)
        inserer_transactions_neo4j(connexion, transactions)

        # ── ÉTAPE 4 : Charger dans NetworkX pour les calculs ───
        graphe = charger_graphe_depuis_neo4j(connexion)

        # ── ÉTAPE 5 : Calculer et classifier ───────────────────
        calculer_scores(graphe)
        classifier(graphe,
                   seuil_fournisseur  = 3,
                   seuil_consommateur = 2,
                   seuil_mini         = 0.15)

        # ── ÉTAPE 6 : Renvoyer les résultats dans Neo4j ────────
        sauvegarder_dans_neo4j(connexion, graphe)

        # ── ÉTAPE 7 : Rapport et visualisation ─────────────────
        afficher_rapport(connexion)
        visualiser_graphe(graphe, nb_personnes)

        duree = time.time() - debut
        print(f"⏱️  Durée totale : {duree:.1f} secondes")

    finally:
        connexion.fermer()
