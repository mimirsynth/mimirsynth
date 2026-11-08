import { useTranslation } from "react-i18next";
import { Tour, type TourStep } from "../ui";

/** The guided tour of the interface (issue 364): eight steps over the navigation, the brain switcher, proposals, the graph, Ask,
 *  administration and the help menu, where it can be replayed. Each target carries its `data-tour` in App.tsx. */
export default function GuidedTour({ opened, onClose, onStep }: { opened: boolean; onClose: (persist: boolean) => void; onStep?: (step: TourStep) => void }) {
  const { t } = useTranslation();
  const steps: TourStep[] = [
    { id: "welcome", title: t("Te damos la bienvenida a MimirSynth"),
      body: t("Un recorrido de un minuto por lo principal de la interfaz. Puedes saltarlo y volver a verlo cuando quieras desde el menú de ayuda.") },
    { id: "nav", target: "nav", title: t("La navegación"),
      body: t("El menú reparte la aplicación en tres partes: Memoria, con lo que el brain sabe; Explorar, para preguntar y recorrer el grafo; y Curación, para revisar lo que entra.") },
    { id: "brain", target: "brain", title: t("Tus brains"),
      body: t("Cada brain es una memoria separada, con sus propias personas y permisos. Aquí eliges con cuál trabajas: todas las pantallas muestran el brain activo.") },
    { id: "proposals", target: "proposals", title: t("Propuestas y curación"),
      body: t("Lo que tus agentes y tus compañeros quieren guardar llega como propuesta. Quien cura el brain la aprueba, la corrige o la rechaza antes de que entre en la memoria.") },
    { id: "graph", target: "graph", title: t("El grafo"),
      body: t("Las entidades y sus relaciones, dibujadas. Pulsa una entidad para ver sus hechos o despliega sus vecinos para seguir el hilo.") },
    { id: "ask", target: "ask", title: t("Preguntar"),
      body: t("Haz una pregunta con tus palabras y obtén una respuesta con los hechos del brain que la respaldan.") },
    { id: "admin", target: "admin", title: t("Administración"),
      body: t("Brains, personas, modelos de IA y ajustes de la instancia. Lo que ves aquí depende de tu rol.") },
    { id: "help", target: "help", title: t("Ayuda"),
      body: t("La documentación, el código, dónde contar un error y este recorrido, por si quieres volver a verlo.") },
  ];
  return <Tour steps={steps} opened={opened} onClose={onClose} onStep={onStep} returnTo="help" />;
}
