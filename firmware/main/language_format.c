#include "language.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

// UI formats use integer, character and string conversions only. Keep numeric
// formatting in libc; strings are translated before interpolation, including
// bounded asset-pool names. No heap or full-message intermediate buffer.
static void append(char *out,size_t size,size_t *used,const char *text,size_t bytes) {
    if(size && *used<size-1) {
        size_t room=size-1-*used,n=bytes<room?bytes:room;
        memcpy(out+*used,text,n);
    }
    *used+=bytes;
}
int language_snprintf(char *out,size_t size,const char *format,...) {
    va_list args;va_start(args,format);
    if(language_get()!=LANGUAGE_EN) {
        int result=vsnprintf(out,size,format,args);va_end(args);return result;
    }
    const char *p=language_text(format);size_t used=0;
    while(*p) {
        if(*p!='%') {const char *first=p;while(*p&&*p!='%')p++;append(out,size,&used,first,p-first);continue;}
        p++;
        if(*p=='%'){append(out,size,&used,p++,1);continue;}
        char spec[24]="%",number[48];size_t n=1;bool left=false,dynamic_precision=false;unsigned width=0;
        while(*p&&strchr("-+ #0",*p)){if(n>=sizeof(spec)-5)goto invalid;left|=*p=='-';spec[n++]=*p++;}
        // All production callers have literal field widths. Precision '*' is
        // used for non-NUL-terminated names in the asset pool.
        while(*p>='0'&&*p<='9'){width=width*10u+(unsigned)(*p-'0');if(width>40||n>=sizeof(spec)-5)goto invalid;spec[n++]=*p++;}
        if(*p=='*')goto invalid;
        int precision=-1;
        if(*p=='.') {
            if(n>=sizeof(spec)-5)goto invalid;
            spec[n++]=*p++;
            if(*p=='*') {precision=va_arg(args,int);p++;dynamic_precision=true;spec[n++]='*';}
            else {precision=0;while(*p>='0'&&*p<='9'){if(precision>1000||n>=sizeof(spec)-5)goto invalid;precision=precision*10+(*p-'0');spec[n++]=*p++;}}
        }
        unsigned length=0;
        if(*p=='l'){length=1;spec[n++]=*p++;if(*p=='l'){length=2;spec[n++]=*p++;}}
        else if(*p=='z'){length=3;spec[n++]=*p++;}
        char type=*p;if(!type)goto invalid;p++;spec[n++]=type;spec[n]=0;
        if(length&&(type=='s'||type=='c'))goto invalid;
        if(type=='s') {
            const char *value=va_arg(args,const char*);if(!value)value="";
            size_t bytes=0;while((precision<0 || bytes<(size_t)precision) && value[bytes])bytes++;
            const char *translated=language_text_n(value,bytes);
            if(translated!=value){value=translated;bytes=strlen(value);}
            size_t padding=width>bytes?width-bytes:0;
            if(!left)for(size_t i=0;i<padding;i++)append(out,size,&used," ",1);
            append(out,size,&used,value,bytes);
            if(left)for(size_t i=0;i<padding;i++)append(out,size,&used," ",1);
        } else if(type=='c') {
            char c=(char)va_arg(args,int);
            if(!left)for(unsigned i=1;i<width;i++)append(out,size,&used," ",1);
            append(out,size,&used,&c,1);
            if(left)for(unsigned i=1;i<width;i++)append(out,size,&used," ",1);
        } else {
            #define FORMAT_VALUE(v) (dynamic_precision ? snprintf(number,sizeof(number),spec,precision,(v)) : snprintf(number,sizeof(number),spec,(v)))
            int count=0;
            if(type=='d'||type=='i') {
                if(length==2)count=FORMAT_VALUE(va_arg(args,long long));
                else if(length==1)count=FORMAT_VALUE(va_arg(args,long));
                else if(length==3)count=FORMAT_VALUE(va_arg(args,ptrdiff_t));
                else count=FORMAT_VALUE(va_arg(args,int));
            } else if(type=='u'||type=='x'||type=='X'||type=='o') {
                if(length==2)count=FORMAT_VALUE(va_arg(args,unsigned long long));
                else if(length==1)count=FORMAT_VALUE(va_arg(args,unsigned long));
                else if(length==3)count=FORMAT_VALUE(va_arg(args,size_t));
                else count=FORMAT_VALUE(va_arg(args,unsigned));
            } else goto invalid;
#undef FORMAT_VALUE
            if(count<0||(size_t)count>=sizeof(number))goto invalid;
            append(out,size,&used,number,(size_t)count);
        }
    }
    va_end(args);
    if(size)out[used<size?used:size-1]=0;
    return used>INT_MAX?-1:(int)used;
invalid:
    va_end(args);if(size)out[0]=0;return -1;
}
