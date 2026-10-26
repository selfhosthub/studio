// ui/shared/lib/file-name.ts

interface NamedFile {
  display_name: string;
  virtual_path?: string | null;
}

interface TypedFile {
  file_extension?: string | null;
  mime_type: string;
}

function hasExtension(name: string): boolean {
  return name.replace(/^\.+|\.+$/g, '').includes('.');
}

// Name shown and saved for a file: display name with an extension, else the stored path tail, else display name
export function getFileName(file: NamedFile): string {
  if (hasExtension(file.display_name)) return file.display_name;
  const tail = file.virtual_path?.split('/').filter(Boolean).pop() ?? '';
  if (hasExtension(tail)) return tail;
  return file.display_name;
}

// Short type label from the extension, else the mime subtype, else FILE
export function getFileTypeLabel(file: TypedFile): string {
  const extension = (file.file_extension ?? '').replace(/^\./, '');
  if (extension) return extension.toUpperCase();
  const subtype = file.mime_type.split('/')[1];
  return subtype ? subtype.toUpperCase() : 'FILE';
}
