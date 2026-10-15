/* Script local minimal pour l'impression native du navigateur.
   Aucune dépendance, aucune requête réseau, aucun script inline : la politique
   de sécurité n'autorise que les scripts servis par l'application elle-même.
   L'impression reste possible sans ce script, via le menu du navigateur. */

document.addEventListener("click", function (evenement) {
  var declencheur = evenement.target.closest("[data-action='print']");
  if (!declencheur) {
    return;
  }
  evenement.preventDefault();
  window.print();
});