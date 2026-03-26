
function Spinner({ small = false }) {
  const sz = small ? 'w-4 h-4' : 'w-7 h-7';
  return (
    <div className="flex justify-center py-4">
      <div className={`${sz} border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin`} />
    </div>
  );
}

export default Spinner;
