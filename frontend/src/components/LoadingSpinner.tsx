export default function LoadingSpinner({ className = '' }: { className?: string }) {
  return (
    <div className={`flex justify-center py-10 ${className}`}>
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
    </div>
  )
}
