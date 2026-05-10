// ui/widgets/instance-view/SortableResourceCard.tsx

'use client';

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import ResourceCard, { CardSize } from './ResourceCard';
import { OrgFile } from '@/shared/types/api';

interface SortableResourceCardProps {
  resource: OrgFile;
  onDownload: (resourceId: string, filename: string) => void;
  onDelete?: (resourceId: string) => void;
  onRegenerate?: (resourceId: string) => void;
  onView?: (resource: OrgFile) => void;
  size?: CardSize;
  showThumbnails?: boolean;
  selectable?: boolean;
  selected?: boolean;
  onSelect?: (resourceId: string) => void;
  isDragEnabled?: boolean;
}

export function SortableResourceCard({
  resource,
  isDragEnabled = true,
  ...props
}: SortableResourceCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: resource.id,
    disabled: !isDragEnabled,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 100 : 'auto' as const,
  };

  return (
    <div ref={setNodeRef} style={style} className="relative group outline-none">
      {/* Drag handle - top right corner, visible on hover */}
      {isDragEnabled && (
        <div
          {...attributes}
          {...listeners}
          className="absolute top-2 right-2 z-10 p-1.5 bg-black/60 hover:bg-black/80 rounded cursor-grab active:cursor-grabbing opacity-0 group-hover:opacity-100 transition-opacity"
          title="Drag to reorder"
        >
          <GripVertical className="w-4 h-4 text-white" />
        </div>
      )}
      <ResourceCard resource={resource} {...props} />
    </div>
  );
}

export default SortableResourceCard;
