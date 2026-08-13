import { useState } from 'react';
import DatePicker from 'react-datepicker';

import { Input } from '../ui';

// Submits a UTC ISO string through a hidden field so uncontrolled FormData reads keep working.
export function DateTimeField({
  defaultValue = null,
  name,
  required = false,
}: {
  defaultValue?: string | null;
  name: string;
  required?: boolean;
}) {
  const [value, setValue] = useState<Date | null>(() => {
    if (!defaultValue) return null;
    const parsed = new Date(defaultValue);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  });

  return (
    <>
      <DatePicker
        customInput={<Input />}
        dateFormat="yyyy-MM-dd HH:mm"
        onChange={setValue}
        placeholderText="Select date and time"
        required={required}
        selected={value}
        showTimeSelect
        timeFormat="HH:mm"
        timeIntervals={15}
        wrapperClassName="w-full"
      />
      <input name={name} type="hidden" value={value?.toISOString() ?? ''} />
    </>
  );
}
