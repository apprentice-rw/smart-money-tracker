import ModuleCard from '../common/ModuleCard.jsx';

export default function ModuleError({ title, message, fullWidth = false }) {
  return (
    <ModuleCard title={title} fullWidth={fullWidth}>
      <p className="text-xs text-red-500 py-4">{message}</p>
    </ModuleCard>
  );
}
