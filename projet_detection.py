import networkx as nx
import matplotlib.pyplot as plt
import math

def transformer_graphe_connexe_sans_boucle(G):
    """
    Transforme un graphe quelconque en graphe connexe, sans boucle, non orienté
    sans supprimer de nœuds.
    Paramètres:
    G: graphe NetworkX (orienté ou non, avec ou sans boucles)
    Retourne:
    H: graphe connexe, sans boucles, non orienté
    """
    # Copier le graphe et le rendre non orienté
    H = nx.Graph(G)

    # Supprimer les boucles
    H.remove_edges_from(nx.selfloop_edges(H))

    # Si le graphe est déjà connexe, on le retourne
    if nx.is_connected(H):
        return H

    # Obtenir les composantes connexes
    composantes_list = list(nx.connected_components(H))

    # Relier les composantes dans l'ordre pour rendre le graphe connexe
    for i in range(len(composantes_list) - 1):
        noeud1 = list(composantes_list[i])[0]
        noeud2 = list(composantes_list[i + 1])[0]
        H.add_edge(noeud1, noeud2)

    return H

def trouver_cliques_bfs(G):
    """
    Trouve toutes les cliques maximales via BFS.
    Principe : on part de chaque arête (clique de taille 2),
    puis on étend niveau par niveau (taille 3, 4, ...)
    """
    from collections import deque

    cliques_maximales = []
    cliques_vues = set()

    # ── Niveau 0 : initialiser la file avec toutes les arêtes ──
    file = deque()

    for u, v in G.edges():
        clique = frozenset([u, v])
        if clique not in cliques_vues:
            cliques_vues.add(clique)
            # candidats = voisins communs de u et v
            candidats = set(G.neighbors(u)) & set(G.neighbors(v))
            file.append((clique, candidats))

    # ── BFS : étendre chaque clique niveau par niveau ──
    while file:
        clique_courante, candidats = file.popleft()
        etendue = False

        for noeud in list(candidats):
            voisins_noeud = set(G.neighbors(noeud))

            # noeud doit être voisin de TOUS les membres de la clique
            if clique_courante.issubset(voisins_noeud):
                nouvelle_clique = clique_courante | {noeud}
                # nouveaux candidats = ceux qui sont voisins de tout le monde
                nouveaux_candidats = candidats & voisins_noeud & set(
                    n for n in candidats
                    if nouvelle_clique.issubset(set(G.neighbors(n)) | {n})
                )

                cle = frozenset(nouvelle_clique)
                if cle not in cliques_vues:
                    cliques_vues.add(cle)
                    file.append((nouvelle_clique, nouveaux_candidats))
                    etendue = True

        # Si aucune extension possible → clique maximale
        if not etendue:
            cliques_maximales.append(set(clique_courante))

    return cliques_maximales


if __name__ == "__main__":
    while True:
        try:
            n = int(input("Entrez le nombre de personnes(dans [500 ; 600]): "))
            if n>1000 or n<500:
                print("    Valeur n'est pas entre 50 et 100")
            else:
                break
        except ValueError:
            print("    Valeur invalide !, veuillez recommencez")
    
    p = math.log(n)/n   
    nbr_possibilite_arete = math.comb(n, 2)
    print(f"Nombre d'arete possible = {nbr_possibilite_arete}")
    print(f"Probabilite = {p}")
    nbr_moyenne_arete = p * nbr_possibilite_arete
    print(f"Nombre moyenne d'arete = {nbr_moyenne_arete}")
    G = nx.gnp_random_graph(n,p)
    G_prim = transformer_graphe_connexe_sans_boucle(G)

    cliques = trouver_cliques_bfs(G_prim)
    for c in cliques:
        print(c)

    nx.draw(G_prim, with_labels=True)
    plt.show()
    
